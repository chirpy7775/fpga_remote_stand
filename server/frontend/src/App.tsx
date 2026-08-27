import { Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import PrivateRoute from "./components/PrivateRoute";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import FpgaPage from "./pages/FpgaPage";
import FpgaControlPage from "./pages/FpgaControlPage";
import ResultsPage from "./pages/ResultsPage";
import FpgaDocPage from "./pages/FpgaDocPage";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<HomePage />} />
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/docs/fpga" element={<FpgaDocPage />} />
        <Route
          path="/fpga"
          element={
            <PrivateRoute allowGuest>
              <FpgaPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/fpga/session"
          element={
            <PrivateRoute>
              <FpgaControlPage />
            </PrivateRoute>
          }
        />
        <Route
          path="/results"
          element={
            <PrivateRoute allowGuest>
              <ResultsPage />
            </PrivateRoute>
          }
        />
      </Route>
    </Routes>
  );
}
