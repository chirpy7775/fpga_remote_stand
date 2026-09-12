import { useEffect, useState } from "react";
import { api, type MonitorJob, type MonitorOverview } from "../lib/api";

const REFRESH_MS = 4000;

const STATUS_STYLE: Record<string, string> = {
  waiting: "bg-gray-100 text-gray-700",
  running: "bg-primary-100 text-primary-700",
  completed: "bg-green-100 text-green-700",
  error: "bg-red-100 text-red-700",
};

const TESTBED_STYLE: Record<string, string> = {
  offline: "bg-gray-100 text-gray-500",
  idle: "bg-green-100 text-green-700",
  busy: "bg-primary-100 text-primary-700",
};

function clock(seconds: number): string {
  const mm = String(Math.floor(seconds / 60)).padStart(2, "0");
  const ss = String(seconds % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function moment(value: string | null): string {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function Card({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div className="bg-white rounded-2xl border border-muted shadow-sm px-5 py-4">
      <div className="text-xs uppercase tracking-wide text-gray-400">{label}</div>
      <div className={`text-3xl font-bold ${accent && value > 0 ? "text-red-600" : "text-primary-700"}`}>
        {value}
      </div>
    </div>
  );
}

function Badge({ text, styles }: { text: string; styles: Record<string, string> }) {
  return (
    <span className={`px-2 py-0.5 rounded-md text-xs font-semibold ${styles[text] ?? "bg-gray-100 text-gray-700"}`}>
      {text}
    </span>
  );
}

export default function MonitorPage() {
  const [data, setData] = useState<MonitorOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openJob, setOpenJob] = useState<MonitorJob | null>(null);

  useEffect(() => {
    const load = () =>
      api
        .monitorOverview()
        .then((overview) => {
          setData(overview);
          setError(null);
        })
        .catch((err) => setError(err instanceof Error ? err.message : "Ошибка загрузки"));
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => clearInterval(timer);
  }, []);

  const showLog = async (job: MonitorJob) => {
    setOpenJob(job);
    try {
      const full = await api.monitorJob(job.id);
      setOpenJob(full.job);
    } catch {
      // оставляем то, что уже есть в списке
    }
  };

  if (error) {
    return <div className="bg-white rounded-2xl border border-muted p-6 text-red-600">{error}</div>;
  }
  if (!data) {
    return <p className="text-gray-400">Загрузка...</p>;
  }

  const { totals } = data;

  return (
    <div className="space-y-6">
      <div className="bg-primary-50 px-6 py-4 rounded-2xl border border-muted flex justify-between items-center">
        <div>
          <h1 className="text-xl font-bold text-primary-700">Мониторинг стендов</h1>
          <p className="text-sm text-gray-500">Обновлено {moment(data.generated_at)}</p>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card label="Стендов онлайн" value={totals.online} />
        <Card label="Активных сессий" value={totals.active_sessions} />
        <Card label="Задач в работе" value={totals.running_jobs} />
        <Card label="В очереди" value={totals.waiting_jobs} />
        <Card label="Заявок за сутки" value={totals.jobs_last_day} />
        <Card label="Ошибок за сутки" value={totals.errors_last_day} accent />
        <Card label="Стендов всего" value={totals.testbeds} />
      </div>

      <section className="bg-white rounded-2xl border border-muted shadow-sm overflow-hidden">
        <h2 className="px-6 py-3 border-b border-muted font-semibold text-primary-700">Стенды</h2>
        <div className="divide-y divide-muted">
          {data.testbeds.map((testbed) => (
            <div key={testbed.id} className="px-6 py-4 space-y-1">
              <div className="flex items-center gap-3">
                <span className="font-semibold">{testbed.name}</span>
                <Badge text={testbed.status} styles={TESTBED_STYLE} />
                {!testbed.is_active && <span className="text-xs text-gray-400">отключён</span>}
                <span className="text-xs text-gray-400 ml-auto">
                  heartbeat {moment(testbed.last_seen_at)}
                </span>
              </div>
              {testbed.current_session && (
                <div className="text-sm text-gray-600">
                  Занял <strong>{testbed.current_session.owner}</strong>, осталось{" "}
                  {clock(testbed.current_session.remaining_seconds)}, пины{" "}
                  {testbed.current_session.pin_states.map((on) => (on ? "1" : "0")).join("")}
                </div>
              )}
              {testbed.current_job && (
                <div className="text-sm text-gray-600">
                  Выполняет <strong>{testbed.current_job.original_filename}</strong> от{" "}
                  {testbed.current_job.owner}
                </div>
              )}
              {!testbed.current_session && !testbed.current_job && (
                <div className="text-sm text-gray-400">Свободен</div>
              )}
            </div>
          ))}
          {data.testbeds.length === 0 && <div className="px-6 py-4 text-gray-400">Стендов нет.</div>}
        </div>
      </section>

      <section className="bg-white rounded-2xl border border-muted shadow-sm overflow-hidden">
        <h2 className="px-6 py-3 border-b border-muted font-semibold text-primary-700">
          Заявки ({data.jobs.length})
        </h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-primary-50 text-left text-gray-600">
              <tr>
                <th className="px-4 py-2">Кто</th>
                <th className="px-4 py-2">Прошивка</th>
                <th className="px-4 py-2">Скрипт</th>
                <th className="px-4 py-2">Стенд</th>
                <th className="px-4 py-2">Статус</th>
                <th className="px-4 py-2">Создана</th>
                <th className="px-4 py-2">Результат</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-muted">
              {data.jobs.map((job) => (
                <tr key={job.id} className="hover:bg-muted/40">
                  <td className="px-4 py-2">
                    {job.owner}
                    {job.is_guest && <span className="ml-1 text-xs text-gray-400">(аноним)</span>}
                  </td>
                  <td className="px-4 py-2">
                    {job.firmware_url ? (
                      <a className="text-primary-700 hover:underline" href={job.firmware_url}>
                        {job.original_filename}
                      </a>
                    ) : (
                      job.original_filename
                    )}
                  </td>
                  <td className="px-4 py-2">
                    {job.instruction_url ? (
                      <a className="text-primary-700 hover:underline" href={job.instruction_url}>
                        {job.instruction_filename}
                      </a>
                    ) : (
                      "—"
                    )}
                  </td>
                  <td className="px-4 py-2">{job.testbed ?? "—"}</td>
                  <td className="px-4 py-2">
                    <Badge text={job.status} styles={STATUS_STYLE} />
                    {job.error_message && (
                      <div className="text-xs text-red-600 max-w-xs truncate" title={job.error_message}>
                        {job.error_message}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-2 whitespace-nowrap text-gray-500">{moment(job.created_at)}</td>
                  <td className="px-4 py-2 space-x-2 whitespace-nowrap">
                    <button onClick={() => showLog(job)} className="text-primary-700 hover:underline">
                      лог
                    </button>
                    {job.result_video_url && (
                      <a className="text-primary-700 hover:underline" href={job.result_video_url}>
                        видео
                      </a>
                    )}
                  </td>
                </tr>
              ))}
              {data.jobs.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-4 text-gray-400">
                    Заявок пока нет.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      {openJob && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center p-6 z-50"
          onClick={() => setOpenJob(null)}
        >
          <div
            className="bg-white rounded-2xl max-w-3xl w-full max-h-[80vh] flex flex-col overflow-hidden"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="px-6 py-3 border-b border-muted flex justify-between items-center">
              <div>
                <div className="font-semibold text-primary-700">{openJob.original_filename}</div>
                <div className="text-xs text-gray-500">
                  {openJob.owner} · {openJob.testbed ?? "без стенда"} · {openJob.status_display}
                </div>
              </div>
              <button onClick={() => setOpenJob(null)} className="text-gray-400 hover:text-gray-700">
                закрыть
              </button>
            </div>
            <pre className="p-4 text-xs bg-gray-900 text-gray-100 overflow-auto flex-1 whitespace-pre-wrap">
              {openJob.execution_log || "Лог пуст."}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
