import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import type { ReactNode } from "react";

export default function PrivateRoute({
  children,
  allowGuest = false,
}: {
  children: ReactNode;
  allowGuest?: boolean;
}) {
  const { user, loading, allowAnonymous } = useAuth();
  if (loading) return <p className="text-gray-400">Загрузка...</p>;
  if (user || (allowGuest && allowAnonymous)) return children;
  return <Navigate to="/login" replace />;
}
