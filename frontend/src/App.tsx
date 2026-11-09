import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import { RequireAuth, RootRedirect } from './auth/RequireAuth'
import { LoginPage } from './features/auth/LoginPage'
import { DoctorAlertsPage } from './features/doctor/DoctorAlertsPage'
import { DoctorPatientsPage } from './features/doctor/DoctorPatientsPage'
import { PatientDetailPage } from './features/doctor/PatientDetailPage'
import { RoleHomePage } from './features/home/RoleHomePage'
import { PatientHistoryPage } from './features/patient/PatientHistoryPage'
import { PatientHomePage } from './features/patient/PatientHomePage'
import { QuestionnairePage } from './features/patient/QuestionnairePage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<RootRedirect />} />
        <Route element={<RequireAuth role="patient" />}>
          <Route path="/patient" element={<PatientHomePage />} />
          <Route path="/patient/questionnaires/:code" element={<QuestionnairePage />} />
          <Route path="/patient/history" element={<PatientHistoryPage />} />
        </Route>
        <Route element={<RequireAuth role="doctor" />}>
          <Route path="/doctor" element={<DoctorPatientsPage />} />
          <Route path="/doctor/patients/:patientId" element={<PatientDetailPage />} />
          <Route path="/doctor/alerts" element={<DoctorAlertsPage />} />
        </Route>
        <Route element={<RequireAuth role="admin" />}>
          <Route path="/admin" element={<RoleHomePage role="admin" />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
