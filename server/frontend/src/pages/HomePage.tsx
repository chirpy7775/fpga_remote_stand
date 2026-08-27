import { Link } from "react-router-dom";
import { Cpu, Cloud } from "lucide-react";

export default function HomePage() {
  return (
    <div className="min-h-full flex items-center justify-center px-4 py-16">
      <div className="max-w-3xl w-full text-center space-y-8">
        <Cloud className="mx-auto text-primary-600" size={40} />
        <h1 className="text-4xl font-extrabold tracking-tight">
          Добро пожаловать в <span className="text-primary-600">FPGA Testbed</span>
        </h1>
        <p className="text-gray-600">
          Загрузите SVF из Quartus и сценарий GPIO, либо займите стенд в реальном времени с камерой и кнопками пинов.
        </p>
        <Link
          to="/fpga"
          className="inline-flex flex-col items-center bg-white p-6 rounded-2xl shadow-md w-64 hover:shadow-xl transition"
        >
          <Cpu size={32} className="text-primary-600 mb-3" />
          <h3 className="text-lg font-semibold">FPGA-платы</h3>
          <p className="text-sm text-gray-500">Асинхронные задачи и синхронная сессия</p>
        </Link>
      </div>
    </div>
  );
}
