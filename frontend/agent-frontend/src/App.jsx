import { NavLink, Route, Routes } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import IssuesList from './pages/IssuesList'
import IssueDetail from './pages/IssueDetail'
import Studies from './pages/Studies'
import StudyDetail from './pages/StudyDetail'
import Countries from './pages/Countries'
import Sites from './pages/Sites'
import Patients from './pages/Patients'
import Shipments from './pages/Shipments'
import Kits from './pages/Kits'
import Admin from './pages/Admin'

const navLinkClass = ({ isActive }) => `nav-link${isActive ? ' active fw-semibold' : ''}`

function App() {
  return (
    <>
      <nav className="navbar app-navbar navbar-expand mb-4 sticky-top">
        <div className="container">
          <span className="navbar-brand mb-0">
            <span className="brand-mark">C</span>
            Clinical Trial Agent
          </span>
          <div className="navbar-nav">
            <NavLink className={navLinkClass} to="/" end>
              Dashboard
            </NavLink>
            <NavLink className={navLinkClass} to="/issues">
              Issues
            </NavLink>
            <NavLink className={navLinkClass} to="/studies">
              Studies
            </NavLink>
            <NavLink className={navLinkClass} to="/admin">
              Admin
            </NavLink>
          </div>
        </div>
      </nav>

      <div className="container pb-5">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/issues" element={<IssuesList />} />
          <Route path="/issues/:issueId" element={<IssueDetail />} />
          <Route path="/studies" element={<Studies />} />
          <Route path="/studies/:studyId" element={<StudyDetail />} />
          <Route path="/countries" element={<Countries />} />
          <Route path="/sites" element={<Sites />} />
          <Route path="/patients" element={<Patients />} />
          <Route path="/shipments" element={<Shipments />} />
          <Route path="/kits" element={<Kits />} />
          <Route path="/admin" element={<Admin />} />
        </Routes>
      </div>
    </>
  )
}

export default App
