import { useEffect, useState } from "react";
import { api, type Testbed } from "../lib/api";

export default function FpgaDocPage() {
  const [testbeds, setTestbeds] = useState<Testbed[]>([]);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let cancelled = false;
    const reload = async () => {
      try {
        const data = await api.testbeds();
        if (cancelled) return;
        setTestbeds(data.testbeds);
        setSelected((prev) => prev || String(data.testbeds[0]?.id ?? ""));
        setError("");
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : "Ошибка загрузки распиновки");
      }
    };
    reload();
    const timer = setInterval(reload, 4000);
    return () => { cancelled = true; clearInterval(timer); };
  }, []);
  const testbed = testbeds.find((item) => String(item.id) === selected);
  return (
    <div className="bg-white rounded-2xl shadow-md border border-muted overflow-hidden">
      <div className="bg-primary-50 px-6 py-3 border-b border-primary-100">
        <h1 className="text-lg font-semibold text-primary-700 uppercase tracking-wide">Документация FPGA</h1>
      </div>
      <div className="p-6 space-y-8 prose max-w-none">
        <section>
          <h2 className="text-xl font-semibold text-primary-700">Прошивка SVF</h2>
          <p>В Quartus после компиляции получится `.sof`. Конвертация:</p>
          <pre className="bg-muted p-4 rounded-md overflow-auto text-sm">{`quartus_cpf -c --operation=BP --voltage=3.3 --freq=10MHz design.sof design.svf`}</pre>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-primary-700">Язык инструкций</h2>
          <p>Текстовый файл, по команде на строку:</p>
          <ul>
            <li><code>pin &lt;1-8&gt; high|low</code> — установить пин</li>
            <li><code>write_frame &lt;N&gt;</code> — подождать N кадров камеры</li>
          </ul>
          <pre className="bg-muted p-4 rounded-md text-sm">{`pin 1 high
write_frame 10
pin 1 low
write_frame 10`}</pre>
        </section>
        <section>
          <h2 className="text-xl font-semibold text-primary-700">Пины Raspberry Pi ↔ DE10-Lite</h2>
          <label className="block">
            Стенд (testbed):{" "}
            <select value={selected} onChange={(event) => setSelected(event.target.value)}>
              {testbeds.map((item) => <option key={item.id} value={item.id}>{item.name} — {item.status}</option>)}
            </select>
          </label>
          {error && <p role="alert">{error}</p>}
          <p>BCM сообщает выбранный агент из GPIO_PINS. «Не сообщён» означает, что агент ещё не передал конфиг. Для офлайн-стенда показан последний полученный конфиг.</p>
          <p>
            Колонка «GPIO DE10» — это индекс <code>GPIO_[n]</code> на JP1, не номер штыря.
            GPIO_19 сидит на контакте 22. Контакт 29 на гребенке — это 3.3&nbsp;V, его к малине не сажать. 5&nbsp;V (контакт 11) тоже нет.
          </p>
          <table className="w-full text-sm border">
            <thead className="bg-primary-100">
              <tr>
                <th className="p-2 border">Логический пин</th>
                <th className="p-2 border">GPIO RPi</th>
                <th className="p-2 border">GPIO DE10</th>
                <th className="p-2 border">FPGA</th>
              </tr>
            </thead>
            <tbody>
              {(testbed?.pin_map ?? []).map(({ index, rpi_bcm, de10_gpio, fpga }) => (
                <tr key={index}>
                  <td className="p-2 border">{index}</td>
                  <td className="p-2 border">{rpi_bcm ?? "Не сообщён"}</td>
                  <td className="p-2 border">{de10_gpio}</td>
                  <td className="p-2 border">{fpga}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>
    </div>
  );
}
