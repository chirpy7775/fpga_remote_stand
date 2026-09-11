import { Clock, Upload } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { api, type Session, type Stand } from "../lib/api";

export default function FpgaPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [stands, setStands] = useState<Stand[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const [svf, setSvf] = useState<File | null>(null);
  const [txt, setTxt] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [messageType, setMessageType] = useState<"success" | "error" | null>(null);
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = async () => {
    const [standsResp, sessionResp] = await Promise.all([
      api.stands(),
      user ? api.session() : Promise.resolve({ session: null }),
    ]);
    setStands(standsResp.stands);
    setSession(sessionResp.session);
    setLoading(false);
  };

  useEffect(() => {
    reload().catch((err) => {
      setMessage(err.message);
      setMessageType("error");
      setLoading(false);
    });
    const timer = setInterval(() => {
      api.stands().then((data) => setStands(data.stands)).catch(() => undefined);
    }, 4000);
    return () => clearInterval(timer);
  }, [user]);

  const submitAsync = async () => {
    if (!selected || !svf || !txt) return;
    const form = new FormData();
    form.append("firmware", svf);
    form.append("instruction", txt);
    form.append("target_agent", String(selected));
    try {
      await api.createJob(form);
      setMessage("Заявка успешно отправлена!");
      setMessageType("success");
      setSvf(null);
      setTxt(null);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка отправки");
      setMessageType("error");
    }
  };

  const takeStand = async (stand: Stand) => {
    try {
      const data = await api.takeStand(stand.id);
      localStorage.setItem("session_token", data.session.token);
      navigate("/fpga/session");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Не удалось занять стенд");
      setMessageType("error");
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div className="bg-white rounded-2xl shadow-md border border-muted overflow-hidden">
        <div className="bg-primary-50 px-6 py-3 border-b border-primary-100 flex items-center gap-2">
          <span className="w-2 h-2 bg-green-500 rounded-full" />
          <Upload className="w-5 h-5 text-primary-600" />
          <h2 className="text-lg font-semibold text-primary-700 uppercase tracking-wide">Асинхронная задача</h2>
        </div>
        <div className="p-6 space-y-6">
          {message && (
            <div className={`p-4 rounded-lg text-center font-semibold ${messageType === "success" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}>
              {message}
            </div>
          )}
          <p className="text-sm text-gray-500">Загрузите SVF из Quartus и txt-инструкцию GPIO</p>
          {loading ? (
            <p className="text-gray-400 text-sm">Загрузка стендов...</p>
          ) : (
            <div className="grid gap-3">
              {stands.map((stand) => (
                <button
                  key={stand.id}
                  onClick={() => setSelected(stand.id)}
                  className={`w-full border rounded-lg p-3 text-left transition ${
                    selected === stand.id ? "bg-primary-100 border-primary-500 text-primary-700 font-bold" : "hover:bg-muted"
                  }`}
                >
                  <div className="flex justify-between">
                    <span>{stand.name}</span>
                    <span className="text-xs uppercase tracking-wide">{stand.status}</span>
                  </div>
                </button>
              ))}
              {stands.length === 0 && <p className="text-gray-400 text-sm">Нет стендов. Пропиши AGENT_TOKEN_stand-1 в server/.env и перезапусти сервер.</p>}
            </div>
          )}
          <div className="space-y-3">
            <p className="text-sm text-gray-500">Файл прошивки SVF</p>
            <input type="file" accept=".svf" onChange={(e) => setSvf(e.target.files?.[0] || null)} />
            <p className="text-sm text-gray-500">Файл инструкции TXT</p>
            <input type="file" accept=".txt" onChange={(e) => setTxt(e.target.files?.[0] || null)} />
          </div>
          {selected && svf && txt && (
            <button className="w-full bg-primary-600 hover:bg-primary-700 text-white font-semibold py-3 rounded-xl" onClick={submitAsync}>
              Отправить
            </button>
          )}
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-md border border-muted overflow-hidden">
        <div className="bg-primary-50 px-6 py-3 border-b border-primary-100 flex items-center gap-2">
          <span className="w-2 h-2 bg-blue-500 rounded-full" />
          <Clock className="w-5 h-5 text-primary-600" />
          <h2 className="text-lg font-semibold text-primary-700 uppercase tracking-wide">Синхронный доступ</h2>
        </div>
        <div className="p-6 space-y-4">
          {session ? (
            <div className="space-y-3">
              <div className="p-4 rounded-lg bg-primary-50 text-primary-800">
                Активная сессия на {session.agent.name}. Осталось {Math.ceil(session.remaining_seconds / 60)} мин.
              </div>
              <button className="w-full bg-green-600 hover:bg-green-700 text-white font-semibold py-3 rounded-lg" onClick={() => navigate("/fpga/session")}>
                Войти в сессию
              </button>
            </div>
          ) : user ? (
            <div className="space-y-3">
              <p className="text-sm text-gray-500">Займите свободный онлайн-стенд на 15 минут.</p>
              {stands.map((stand) => (
                <button
                  key={stand.id}
                  disabled={stand.status !== "idle"}
                  onClick={() => takeStand(stand)}
                  className="w-full border rounded-lg p-3 text-left disabled:opacity-50 hover:bg-primary-50"
                >
                  {stand.name} — {stand.status}
                </button>
              ))}
            </div>
          ) : (
            <div className="space-y-3">
              <p className="text-sm text-gray-500">Живая сессия с камерой доступна после входа в аккаунт.</p>
              <Link to="/login" className="block w-full text-center bg-primary-600 hover:bg-primary-700 text-white font-semibold py-3 rounded-lg">
                Войти для синхронного доступа
              </Link>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
