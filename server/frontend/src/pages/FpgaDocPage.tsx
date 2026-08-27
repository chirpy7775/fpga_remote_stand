const PIN_ROWS = [
  [1, 21, 19, "PIN_W11"],
  [2, 20, 21, "PIN_AA10"],
  [3, 16, 23, "PIN_Y8"],
  [4, 12, 25, "PIN_Y7"],
  [5, 1, 27, "PIN_Y6"],
  [6, 7, 29, "PIN_Y5"],
  [7, 8, 31, "PIN_Y4"],
  [8, 25, 33, "PIN_Y3"],
];

export default function FpgaDocPage() {
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
              {PIN_ROWS.map(([index, rpi, de10, fpga]) => (
                <tr key={index}>
                  <td className="p-2 border">{index}</td>
                  <td className="p-2 border">{rpi}</td>
                  <td className="p-2 border">{de10}</td>
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
