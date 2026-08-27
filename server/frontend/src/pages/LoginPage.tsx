import { FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function LoginPage() {
  const { login, allowAnonymous } = useAuth();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    try {
      await login(username, password);
      navigate("/fpga");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    }
  };

  return (
    <div className="max-w-md mx-auto bg-white rounded-2xl shadow-md border border-muted p-8">
      <h1 className="text-2xl font-bold text-primary-700 mb-6">Вход</h1>
      {error && <div className="mb-4 p-3 rounded-lg bg-red-50 text-red-700 text-sm">{error}</div>}
      <form onSubmit={onSubmit} className="space-y-4">
        <input
          className="w-full border rounded-lg px-3 py-2"
          placeholder="Имя пользователя"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
        />
        <input
          className="w-full border rounded-lg px-3 py-2"
          type="password"
          placeholder="Пароль"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
        <button className="w-full bg-primary-600 hover:bg-primary-700 text-white font-semibold py-2 rounded-lg">
          Войти
        </button>
      </form>
      <p className="text-sm text-gray-500 mt-4">
        Нет аккаунта? <Link className="text-primary-600" to="/register">Регистрация</Link>
        {allowAnonymous && (
          <>
            {" · "}
            <Link className="text-primary-600" to="/fpga">Продолжить без регистрации</Link>
          </>
        )}
      </p>
    </div>
  );
}
