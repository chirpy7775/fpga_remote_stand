import { useEffect, useState } from "react";
import { useAuth } from "../context/AuthContext";
import { api, type Job } from "../lib/api";

export default function ResultsPage() {
  const { user } = useAuth();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = () => api.jobs().then((data) => setJobs(data.jobs)).catch((err) => setError(err.message));
    load();
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="bg-white rounded-2xl shadow-md border border-muted overflow-hidden">
      <div className="bg-primary-50 px-6 py-3 border-b border-primary-100">
        <h1 className="text-lg font-semibold text-primary-700 uppercase tracking-wide">Мои заявки</h1>
      </div>
      <div className="p-6">
        {error && <p className="text-red-600 mb-4">{error}</p>}
        {!user && (
          <p className="text-sm text-gray-500 mb-4">Гостевой режим: история заявок хранится только в этом браузере.</p>
        )}
        {jobs.length === 0 ? (
          <p className="text-gray-400">Пока задач нет.</p>
        ) : (
          <div className="space-y-4">
            {jobs.map((job) => (
              <div key={job.id} className="border rounded-xl p-4 space-y-2">
                <div className="flex justify-between gap-4">
                  <div>
                    <div className="font-semibold">{job.original_filename}</div>
                    <div className="text-sm text-gray-500">{job.instruction_filename} · {job.target_agent?.name}</div>
                  </div>
                  <span className="text-sm font-semibold text-primary-700">{job.status_display}</span>
                </div>
                {job.error_message && <div className="text-sm text-red-600">{job.error_message}</div>}
                {job.execution_log && <pre className="text-xs bg-gray-900 text-gray-100 p-3 rounded-lg overflow-auto max-h-40">{job.execution_log}</pre>}
                {job.result_video_url && (
                  <video controls className="w-full max-w-xl rounded-xl">
                    <source src={job.result_video_url} />
                  </video>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
