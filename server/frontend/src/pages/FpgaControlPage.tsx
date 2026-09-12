import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type Session } from "../lib/api";

export default function FpgaControlPage() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const navigate = useNavigate();
  const [session, setSession] = useState<Session | null>(null);
  const [pins, setPins] = useState<boolean[]>(Array(8).fill(false));
  const [file, setFile] = useState<File | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      const data = await api.session();
      if (cancelled) return;
      if (!data.session) {
        navigate("/fpga");
        return;
      }
      localStorage.setItem("session_token", data.session.token);
      setSession(data.session);
      setPins(data.session.pin_states);
    };
    load().catch(() => navigate("/fpga"));
    const timer = setInterval(load, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [navigate]);

  useEffect(() => {
    if (!session) return;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    const img = new Image();
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const socket = new WebSocket(`${proto}://${location.host}/ws/camera/viewer/?token=${session.token}`);
    socket.binaryType = "blob";
    socket.onmessage = (event) => {
      if (!canvas || !ctx) return;
      const blob = event.data as Blob;
      const url = URL.createObjectURL(blob);
      img.onload = () => {
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        URL.revokeObjectURL(url);
      };
      img.src = url;
    };
    return () => socket.close();
  }, [session?.token]);

  useEffect(() => {
    if (!session) return;
    const interval = setInterval(() => {
      setSession((prev) => {
        if (!prev) return prev;
        const remaining = Math.max(0, prev.remaining_seconds - 1);
        if (remaining <= 0) setExpired(true);
        return { ...prev, remaining_seconds: remaining };
      });
    }, 1000);
    return () => clearInterval(interval);
  }, [session?.id]);

  const togglePin = async (index: number) => {
    const next = !pins[index];
    const updated = [...pins];
    updated[index] = next;
    setPins(updated);
    try {
      const data = await api.setPin(index + 1, next ? "high" : "low");
      setPins(data.session.pin_states);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка пина");
    }
  };

  const sendFlash = async () => {
    if (!file) return;
    const form = new FormData();
    form.append("flash_file", file);
    try {
      await api.flashSession(form);
      setMessage("Файл прошивки отправлен на стенд");
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Ошибка прошивки");
    }
  };

  const leave = async () => {
    await api.releaseSession().catch(() => undefined);
    localStorage.removeItem("session_token");
    navigate("/fpga");
  };

  const remaining = session?.remaining_seconds ?? 0;
  const mm = String(Math.floor(remaining / 60)).padStart(2, "0");
  const ss = String(remaining % 60).padStart(2, "0");

  return (
    <div className="space-y-6">
      <div className="bg-primary-50 px-6 py-4 rounded-2xl border border-muted flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold text-primary-700">Управление FPGA</h1>
          <p className="text-sm text-gray-500">Трансляция и пины {session?.agent.name}</p>
        </div>
        <div className="flex items-center gap-4">
          <div className={`text-xl font-semibold ${expired ? "text-red-600" : "text-primary-700"}`}>
            Осталось {mm}:{ss}
          </div>
          <button onClick={leave} className="bg-primary-600 hover:bg-primary-700 text-white font-semibold px-4 py-2 rounded-md">
            Выйти
          </button>
        </div>
      </div>

      <div className="bg-white rounded-2xl shadow-md border p-6 flex flex-col items-center">
        <h2 className="text-2xl font-bold mb-4 text-primary-700">Онлайн трансляция</h2>
        <canvas ref={canvasRef} width={640} height={480} className="bg-black rounded-xl" />
      </div>

      <div className="bg-white rounded-2xl shadow-md border p-6 grid md:grid-cols-2 gap-6">
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-primary-700">Прошивка платы</h2>
          <input type="file" accept=".svf" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          <button onClick={sendFlash} className="w-full bg-primary-600 hover:bg-primary-700 text-white font-semibold py-2 rounded-lg">
            Отправить файл
          </button>
          {message && <div className="p-3 rounded-lg bg-primary-50 text-primary-800 text-sm">{message}</div>}
        </div>
        <div className="space-y-4">
          <h2 className="text-xl font-semibold text-primary-700">Управление пинами</h2>
          <div className="grid grid-cols-2 gap-4">
            {pins.map((isActive, index) => (
              <button
                key={index}
                onClick={() => togglePin(index)}
                className={`py-4 px-6 rounded-xl font-bold text-lg ${isActive ? "bg-green-500 text-white" : "bg-gray-200 text-gray-700"}`}
              >
                Пин {index + 1}
                <span className="block text-xs font-normal">
                  BCM {session?.pin_map[index]?.rpi_bcm ?? "не сообщён"}
                </span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
