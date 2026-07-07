from __future__ import annotations

import base64
import html
import inspect
import os
import re
from dataclasses import dataclass
from email.mime.text import MIMEText
from email.utils import getaddresses
from functools import lru_cache
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# Fixed addresses requested for this MVP.
SENDER_EMAIL = "rudrank2004@gmail.com"
RECIPIENT_EMAIL = "rudymer313@gmail.com"
EXPECTED_REPLY_SENDER = RECIPIENT_EMAIL
EXPECTED_REPLY_RECIPIENT = SENDER_EMAIL

ISSUE_SUBJECT_PATTERN = re.compile(r"\[CTA-ISSUE-(\d+)\]", re.IGNORECASE)
DEFAULT_GMAIL_SCOPES = ["https://mail.google.com/"]


class GmailToolkitConfigurationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SentEmail:
    # Keep message_id as the primary field for compatibility with previous tests.
    message_id: str | None
    sender: str
    recipient: str
    subject: str
    gmail_thread_id: str | None = None
    raw_tool_result: str = ""

    @property
    def gmail_message_id(self) -> str | None:
        return self.message_id


@dataclass(frozen=True)
class ReceivedReply:
    uid: str
    message_id: str | None
    in_reply_to: str | None
    references: tuple[str, ...]
    issue_id_from_subject: int | None
    sender: str
    recipient: str
    subject: str
    body: str
    gmail_message_id: str | None = None
    gmail_thread_id: str | None = None


class GmailToolkitEmailClient:
    """
    Gmail adapter backed by LangChain's OAuth credential helpers and the raw Gmail API.

    Sends go through the Gmail API directly as HTML so durable message/thread IDs are
    available for audit and duplicate protection; the same API resource is reused for
    polling, message hydration, and marking replies as processed.
    """

    def __init__(self) -> None:
        self.api_resource = self._build_api_resource()

    def send_email(
        self,
        *,
        issue_id: int,
        subject: str,
        body: str,
        reply_to_message_id: str | None = None,
    ) -> SentEmail:
        sent_message = self._send_html_email_via_gmail_api(
            to=RECIPIENT_EMAIL,
            subject=subject,
            body=body,
            reply_to_message_id=reply_to_message_id,
        )
        sent_id = sent_message.get("id")
        thread_id = sent_message.get("threadId")
        return SentEmail(
            message_id=str(sent_id) if sent_id else None,
            sender=SENDER_EMAIL,
            recipient=RECIPIENT_EMAIL,
            subject=subject,
            gmail_thread_id=str(thread_id) if thread_id else None,
            raw_tool_result=f"Gmail API HTML send result: {sent_message}",
        )

    def fetch_unread_replies(self, *, max_results: int = 25) -> list[ReceivedReply]:
        query = (
            f"from:{EXPECTED_REPLY_SENDER} "
            f"to:{EXPECTED_REPLY_RECIPIENT} "
            "(subject:CTA-ISSUE OR CTA-ISSUE) "
            "newer_than:30d -in:trash"
        )
        response = (
            self.api_resource.users()
            .messages()
            .list(userId="me", q=query, maxResults=max_results)
            .execute()
        )
        replies: list[ReceivedReply] = []
        for item in response.get("messages", []) or []:
            gmail_message_id = item.get("id")
            if not gmail_message_id:
                continue
            message = (
                self.api_resource.users()
                .messages()
                .get(userId="me", id=gmail_message_id, format="full")
                .execute()
            )
            reply = self._parse_gmail_message(message)
            if reply is not None:
                replies.append(reply)
        return replies

    def mark_reply_seen(self, gmail_message_id: str) -> None:
        self.api_resource.users().messages().modify(
            userId="me",
            id=gmail_message_id,
            body={"removeLabelIds": ["UNREAD"]},
        ).execute()

    def _build_api_resource(self):
        get_credentials, build_resource = _import_gmail_credential_helpers()
        credentials_file = os.getenv("GMAIL_CREDENTIALS_FILE", "credentials.json")
        token_file = os.getenv("GMAIL_TOKEN_FILE", "token.json")
        scopes = [
            scope.strip()
            for scope in os.getenv("GMAIL_SCOPES", " ".join(DEFAULT_GMAIL_SCOPES)).split()
            if scope.strip()
        ] or DEFAULT_GMAIL_SCOPES
        try:
            credentials = _get_gmail_credentials_compat(
                get_credentials=get_credentials,
                credentials_file=credentials_file,
                token_file=token_file,
                scopes=scopes,
            )
            return build_resource(credentials=credentials)
        except Exception as exc:  # noqa: BLE001 - normalize OAuth failures.
            raise GmailToolkitConfigurationError(
                "Could not build the Gmail API resource. Ensure credentials.json/token.json are configured. "
                f"Original error: {exc}"
            ) from exc

    def _send_html_email_via_gmail_api(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        reply_to_message_id: str | None,
    ) -> dict[str, Any]:
        """Send a real text/html email so paragraph breaks survive Gmail rendering."""
        html_body = _text_to_html_email(body)
        message = MIMEText(html_body, "html", "utf-8")
        message["To"] = to
        message["From"] = SENDER_EMAIL
        message["Subject"] = subject

        thread_id, in_reply_to, references = self._reply_metadata(reply_to_message_id)
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
        if references:
            message["References"] = references

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        send_body: dict[str, Any] = {"raw": raw}
        if thread_id:
            send_body["threadId"] = thread_id

        return (
            self.api_resource.users()
            .messages()
            .send(userId="me", body=send_body)
            .execute()
        )

    def _reply_metadata(self, reply_to_message_id: str | None) -> tuple[str | None, str | None, str | None]:
        if not reply_to_message_id:
            return None, None, None

        try:
            original_message = (
                self.api_resource.users()
                .messages()
                .get(userId="me", id=reply_to_message_id, format="metadata")
                .execute()
            )
        except Exception:  # noqa: BLE001 - tolerate non-Gmail/RFC message ids.
            if reply_to_message_id.startswith("<") and reply_to_message_id.endswith(">"):
                return None, reply_to_message_id, reply_to_message_id
            return None, None, None

        headers = _headers_dict(original_message)
        thread_id = original_message.get("threadId")
        original_rfc_message_id = headers.get("message-id")
        original_references = headers.get("references", "").strip()

        if original_rfc_message_id and original_references:
            references = f"{original_references} {original_rfc_message_id}".strip()
        else:
            references = original_rfc_message_id or original_references or None

        return (
            str(thread_id) if thread_id else None,
            original_rfc_message_id,
            references,
        )

    def _parse_gmail_message(self, message: dict[str, Any]) -> ReceivedReply | None:
        headers = _headers_dict(message)
        senders = {address.lower() for _, address in getaddresses([headers.get("from", "")]) if address}
        recipients = {
            address.lower()
            for _, address in getaddresses([headers.get("to", ""), headers.get("cc", "")])
            if address
        }
        if EXPECTED_REPLY_SENDER not in senders:
            return None
        if EXPECTED_REPLY_RECIPIENT not in recipients:
            return None
        subject = headers.get("subject", "")
        body = _extract_body_from_payload(message.get("payload") or {})
        issue_id = _issue_id_from_text(subject) or _issue_id_from_text(body)
        if issue_id is None:
            return None
        references = tuple(str(headers.get("references", "")).split())
        gmail_message_id = message.get("id")
        return ReceivedReply(
            uid=str(gmail_message_id),
            message_id=str(gmail_message_id) if gmail_message_id else None,
            in_reply_to=headers.get("in-reply-to"),
            references=references,
            issue_id_from_subject=issue_id,
            sender=EXPECTED_REPLY_SENDER,
            recipient=EXPECTED_REPLY_RECIPIENT,
            subject=subject,
            body=_clean_reply_body(body),
            gmail_message_id=str(gmail_message_id) if gmail_message_id else None,
            gmail_thread_id=message.get("threadId"),
        )


def _get_gmail_credentials_compat(*, get_credentials, credentials_file: str, token_file: str, scopes: list[str]):
    """Call LangChain's get_gmail_credentials across package versions.

    Different langchain-google-community / langchain-community releases use
    different keyword names for the OAuth client secret file. Some accept
    client_secrets_file, while newer installs may accept credentials_file or
    credentials_path. This compatibility wrapper prevents the worker from dying
    before it can send pending follow-ups.
    """
    signature = inspect.signature(get_credentials)
    parameter_names = set(signature.parameters)

    kwargs: dict[str, Any] = {}

    if "scopes" in parameter_names:
        kwargs["scopes"] = scopes

    for token_arg in ("token_file", "token_path", "token_file_path"):
        if token_arg in parameter_names:
            kwargs[token_arg] = token_file
            break

    for credentials_arg in (
        "client_secrets_file",
        "credentials_file",
        "credentials_path",
        "client_secret_file",
        "client_secrets_path",
    ):
        if credentials_arg in parameter_names:
            kwargs[credentials_arg] = credentials_file
            break

    try:
        return get_credentials(**kwargs)
    except TypeError:
        # Last-resort fallbacks for versions whose wrappers expose a flexible
        # signature but still expect one of these documented keyword shapes.
        attempts = [
            {"token_file": token_file, "scopes": scopes, "credentials_file": credentials_file},
            {"token_file": token_file, "scopes": scopes, "credentials_path": credentials_file},
            {"token_file": token_file, "scopes": scopes, "client_secrets_file": credentials_file},
        ]
        last_error: TypeError | None = None
        for attempt in attempts:
            try:
                return get_credentials(**attempt)
            except TypeError as exc:
                last_error = exc
        raise last_error or RuntimeError("Could not call get_gmail_credentials")


def _import_gmail_credential_helpers():
    import_errors: list[str] = []

    utils_candidates = [
        ("langchain_google_community.gmail.utils", "get_gmail_credentials", "build_resource_service"),
        ("langchain_google_community.tools.gmail.utils", "get_gmail_credentials", "build_resource_service"),
        ("langchain_community.tools.gmail.utils", "get_gmail_credentials", "build_resource_service"),
    ]

    get_credentials = None
    build_resource = None
    for module_name, get_name, build_name in utils_candidates:
        try:
            module = __import__(module_name, fromlist=[get_name, build_name])
            get_credentials = getattr(module, get_name)
            build_resource = getattr(module, build_name)
            break
        except Exception as exc:  # noqa: BLE001
            import_errors.append(f"{module_name}: {exc}")

    if get_credentials is None or build_resource is None:
        raise GmailToolkitConfigurationError(
            "Could not import Gmail credential helpers. Install langchain-google-community or langchain-community. "
            + " | ".join(import_errors)
        )
    return get_credentials, build_resource


@lru_cache(maxsize=1)
def get_email_client() -> GmailToolkitEmailClient:
    return GmailToolkitEmailClient()


def send_email(
    *,
    issue_id: int,
    subject: str,
    body: str,
    reply_to_message_id: str | None = None,
) -> SentEmail:
    return get_email_client().send_email(
        issue_id=issue_id,
        subject=subject,
        body=body,
        reply_to_message_id=reply_to_message_id,
    )


def fetch_unread_replies() -> list[ReceivedReply]:
    return get_email_client().fetch_unread_replies()


def mark_reply_seen(uid: str) -> None:
    get_email_client().mark_reply_seen(uid)


def _tagged_subject(issue_id: int, subject: str) -> str:
    clean = re.sub(r"\[CTA-ISSUE-\d+\]\s*", "", subject).strip()
    return f"[CTA-ISSUE-{issue_id}] {clean}"


def _headers_dict(message: dict[str, Any]) -> dict[str, str]:
    headers = message.get("payload", {}).get("headers", []) or []
    return {
        str(header.get("name", "")).lower(): str(header.get("value", ""))
        for header in headers
    }


def _issue_id_from_text(text: str) -> int | None:
    match = ISSUE_SUBJECT_PATTERN.search(text or "")
    if match:
        return int(match.group(1))
    match = re.search(r"CTA-ISSUE-(\d+)", text or "", re.IGNORECASE)
    return int(match.group(1)) if match else None


def _text_to_html_email(text: str) -> str:
    """Convert Gemini's plain-text line breaks into safe HTML paragraphs."""
    normalized = str(text or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        return "<html><body></body></html>"

    paragraphs = re.split(r"\n\s*\n+", normalized)
    html_paragraphs: list[str] = []

    for paragraph in paragraphs:
        lines = [html.escape(line.strip()) for line in paragraph.split("\n")]
        escaped_paragraph = "<br>".join(line for line in lines if line)
        if escaped_paragraph:
            html_paragraphs.append(f"<p>{escaped_paragraph}</p>")

    return (
        '<html><body style="font-family: Arial, sans-serif; line-height: 1.5;">'
        + "\n".join(html_paragraphs)
        + "</body></html>"
    )


def _extract_body_from_payload(payload: dict[str, Any]) -> str:
    mime_type = payload.get("mimeType", "")
    body = payload.get("body", {}) or {}
    data = body.get("data")
    if data and mime_type in {"text/plain", "text/html", ""}:
        return _decode_gmail_body(data)
    for part in payload.get("parts", []) or []:
        if part.get("mimeType") == "text/plain":
            data = (part.get("body") or {}).get("data")
            if data:
                return _decode_gmail_body(data)
    for part in payload.get("parts", []) or []:
        nested = _extract_body_from_payload(part)
        if nested:
            return nested
    return ""


def _decode_gmail_body(data: str) -> str:
    padding = "=" * (-len(data) % 4)
    decoded = base64.urlsafe_b64decode((data + padding).encode("ascii"))
    return decoded.decode("utf-8", errors="replace")


def _clean_reply_body(body: str) -> str:
    lines: list[str] = []
    for line in str(body).splitlines():
        stripped = line.strip()
        if stripped.startswith(">"):
            continue
        if re.match(r"^On .+ wrote:$", stripped):
            break
        if stripped.startswith("Workflow token: CTA-ISSUE-"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()