import { BrowserRouter, Navigate, Route, Routes } from 'react-router'

import { RequireAuth, RootRedirect } from './auth/RequireAuth'
import { LoginPage } from './features/auth/LoginPage'
import { RoleHomePage } from './features/home/RoleHomePage'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<RootRedirect />} />
        <Route element={<RequireAuth role="patient" />}>
          <Route path="/patient" element={<RoleHomePage role="patient" />} />
        </Route>
        <Route element={<RequireAuth role="doctor" />}>
          <Route path="/doctor" element={<RoleHomePage role="doctor" />} />
        </Route>
        <Route element={<RequireAuth role="admin" />}>
          <Route path="/admin" element={<RoleHomePage role="admin" />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
