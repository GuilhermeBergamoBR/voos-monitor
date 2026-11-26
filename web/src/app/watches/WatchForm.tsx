import { saveWatch } from "./actions";

type Watch = Record<string, unknown> | null;

const field = "rounded-lg border border-neutral-300 dark:border-neutral-700 bg-transparent px-3 py-2 w-full";
const label = "text-sm text-neutral-600 dark:text-neutral-300";

function v(w: Watch, k: string, d: string | number = "") {
  const x = w?.[k];
  if (Array.isArray(x)) return x.join(", ");
  return x === null || x === undefined ? String(d) : String(x);
}

export default function WatchForm({ watch }: { watch: Watch }) {
  const flexible = watch?.date_mode === "flexible";
  return (
    <form action={saveWatch} className="grid gap-4">
      {watch?.id ? <input type="hidden" name="id" value={String(watch.id)} /> : null}
      <div>
        <label className={label} htmlFor="name">Nome</label>
        <input id="name" name="name" required className={field} defaultValue={v(watch, "name")}
               placeholder="Lisboa em março" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label} htmlFor="origins">Origens (IATA)</label>
          <input id="origins" name="origins" className={field} defaultValue={v(watch, "origins", "GRU, CGH")} />
        </div>
        <div>
          <label className={label} htmlFor="destinations">Destinos (IATA)</label>
          <input id="destinations" name="destinations" required className={field}
                 defaultValue={v(watch, "destinations")} placeholder="LIS, OPO" />
        </div>
      </div>
      <fieldset className="grid gap-3">
        <legend className={label}>Datas</legend>
        <select name="date_mode" defaultValue={flexible ? "flexible" : "fixed"} className={field}>
          <option value="fixed">Datas fixas</option>
          <option value="flexible">Flexíveis (Fase 2)</option>
        </select>
        <div className="grid grid-cols-2 gap-3">
          <input type="date" name="depart_date" aria-label="Ida" className={field} defaultValue={v(watch, "depart_date")} />
          <input type="date" name="return_date" aria-label="Volta" className={field} defaultValue={v(watch, "return_date")} />
          <input type="date" name="depart_from" aria-label="Ida a partir de" className={field} defaultValue={v(watch, "depart_from")} />
          <input type="date" name="depart_to" aria-label="Ida até" className={field} defaultValue={v(watch, "depart_to")} />
          <input type="number" name="nights_min" min={1} placeholder="noites mín." className={field} defaultValue={v(watch, "nights_min")} />
          <input type="number" name="nights_max" min={1} placeholder="noites máx." className={field} defaultValue={v(watch, "nights_max")} />
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" name="one_way" defaultChecked={watch?.one_way === true} /> Só ida
        </label>
      </fieldset>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={label} htmlFor="adults">Adultos</label>
          <input id="adults" name="adults" type="number" min={1} max={9} className={field} defaultValue={v(watch, "adults", 2)} />
        </div>
        <div>
          <label className={label} htmlFor="cabin">Cabine</label>
          <select id="cabin" name="cabin" className={field} defaultValue={v(watch, "cabin", "economy")}>
            <option value="economy">Econômica</option>
            <option value="premium_economy">Premium economy</option>
            <option value="business">Executiva</option>
            <option value="first">Primeira</option>
          </select>
        </div>
        <div>
          <label className={label} htmlFor="max_stops">Escalas máx.</label>
          <input id="max_stops" name="max_stops" type="number" min={0} max={3} className={field} defaultValue={v(watch, "max_stops", 1)} />
        </div>
        <div>
          <label className={label} htmlFor="max_duration_hours">Duração máx. (h)</label>
          <input id="max_duration_hours" name="max_duration_hours" type="number" className={field} defaultValue={v(watch, "max_duration_hours")} />
        </div>
        <div>
          <label className={label} htmlFor="budget_total">Orçamento total (R$)</label>
          <input id="budget_total" name="budget_total" type="number" className={field} defaultValue={v(watch, "budget_total")} />
        </div>
        <div>
          <label className={label} htmlFor="sensitivity">Sensibilidade</label>
          <select id="sensitivity" name="sensitivity" className={field} defaultValue={v(watch, "sensitivity", "balanced")}>
            <option value="conservative">Conservadora (20%)</option>
            <option value="balanced">Equilibrada (12%)</option>
            <option value="aggressive">Agressiva (7%)</option>
          </select>
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="need_checked_bag" defaultChecked={watch?.need_checked_bag === true} /> Preciso de bagagem despachada
      </label>
      <button className="rounded-lg bg-sky-600 px-4 py-2 font-medium text-white hover:bg-sky-700">Salvar</button>
    </form>
  );
}
