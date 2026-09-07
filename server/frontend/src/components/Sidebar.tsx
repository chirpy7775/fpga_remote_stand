import { NavLink, useNavigate } from "react-router-dom";
import { Cpu, BarChartHorizontal, Home, Book, Activity } from "lucide-react";
import { useAuth } from "../context/AuthContext";

const items = [
  { to: "/", label: "Главная", icon: Home },
  { to: "/fpga", label: "FPGA", icon: Cpu },
  { to: "/results", label: "Заявки", icon: BarChartHorizontal },
  { to: "/docs/fpga", label: "Документация", icon: Book },
];

const staffItems = [{ to: "/monitor", label: "Мониторинг", icon: Activity }];

export default function Sidebar() {
  const { user, logout, allowAnonymous } = useAuth();
  const navigate = useNavigate();
  const links = user?.is_staff ? [...items, ...staffItems] : items;

  return (
    <aside className="h-screen overflow-y-auto bg-white border-r border-muted px-4 py-6 shadow-sm flex flex-col w-64 shrink-0">
      <NavLink to="/" className="flex items-center gap-3 px-2 mb-10">
        <div className="w-12 h-12 rounded-2xl bg-primary-600 text-white flex items-center justify-center shadow-lg">
          <Cpu size={26} />
        </div>
        <div>
          <div className="font-bold text-primary-700 leading-tight">FPGA Testbed</div>
          <div className="text-xs text-gray-400">удалённый стенд</div>
        </div>
      </NavLink>

      <nav className="flex-1 space-y-1">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `group flex items-center gap-3 px-4 py-2 rounded-lg transition-colors ${
                isActive ? "bg-primary-100 text-primary-700 font-semibold" : "text-gray-600 hover:bg-muted"
              }`
            }
          >
            <Icon size={20} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="pt-6 border-t border-muted">
        {user ? (
          <div className="px-2 space-y-2">
            <div className="text-sm font-semibold text-gray-800">{user.username}</div>
            <button onClick={() => logout().then(() => navigate("/"))} className="text-xs text-red-500 hover:underline">
              Выйти
            </button>
          </div>
        ) : (
          <div className="px-2 space-y-2">
            {allowAnonymous && <div className="text-sm font-semibold text-gray-800">Гость</div>}
            <button
              onClick={() => navigate("/login")}
              className="w-full border border-primary-600 text-primary-600 font-semibold py-2 rounded-md hover:bg-primary-50"
            >
              Войти
            </button>
          </div>
        )}
      </div>
    </aside>
  );
}
