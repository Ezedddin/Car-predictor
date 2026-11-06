import { useEffect, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

const BRANDSTOF = {
  petrol: 'Benzine', diesel: 'Diesel', hybrid: 'Hybride', electric: 'Elektrisch', lpg: 'LPG', other: 'Overig',
}
const TRANSMISSIE = { manual: 'Handgeschakeld', automatic: 'Automaat', other: 'Overig' }

const euro = (v) => v.toLocaleString('nl-NL', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 })
const getal = (v) => v.toLocaleString('nl-NL', { maximumFractionDigits: 0 })

// Maanden in de vorm "2028-03"
const maandenTussen = (van, tot) => {
  const [j1, m1] = van.split('-').map(Number)
  const [j2, m2] = tot.split('-').map(Number)
  return (j2 - j1) * 12 + (m2 - m1)
}
const plusMaanden = (maand, n) => {
  const [j, m] = maand.split('-').map(Number)
  const d = new Date(j, m - 1 + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}
const maandNaam = (maand) => {
  const [j, m] = maand.split('-').map(Number)
  return new Date(j, m - 1).toLocaleDateString('nl-NL', { month: 'short', year: 'numeric' })
}
const KM_PER_JAAR = 15000

async function api(pad, opties) {
  const res = await fetch(pad, opties)
  const body = await res.json()
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(', ') : body.detail
    throw new Error(detail || `Fout ${res.status}`)
  }
  return body
}

export default function App() {
  const [opties, setOpties] = useState(null)
  const [form, setForm] = useState({
    merk: 'Volkswagen', model: 'Golf', bouwjaar: 2020, brandstof: 'petrol', transmissie: 'manual',
    km: 90000, verkoop: '', km_verkoop: 105000, inflatie: 0,
  })
  // Zolang de gebruiker de km-stand bij verkoop niet zelf invult, rekenen we hem uit (15.000 km per jaar)
  const [kmVerkoopZelf, setKmVerkoopZelf] = useState(false)
  const [resultaat, setResultaat] = useState(null)
  const [fout, setFout] = useState(null)
  const [bezig, setBezig] = useState(false)

  useEffect(() => {
    api('/api/opties').then((o) => {
      setOpties(o)
      setForm((f) => ({ ...f, verkoop: plusMaanden(o.nu, 12) }))
    }).catch(() => setFout('Geen verbinding met de server (app/api).'))
  }, [])

  const verkoopMaanden = opties && form.verkoop ? maandenTussen(opties.nu, form.verkoop) : 12

  useEffect(() => {
    if (kmVerkoopZelf) return
    const km = Number(form.km) + Math.round((KM_PER_JAAR * verkoopMaanden) / 12 / 1000) * 1000
    setForm((f) => ({ ...f, km_verkoop: km }))
  }, [form.km, verkoopMaanden, kmVerkoopZelf])

  // Meest voorkomende brandstof en transmissie als standaard zodra het model verandert
  useEffect(() => {
    if (!form.merk || !form.model) return
    const q = new URLSearchParams({ merk: form.merk, model: form.model })
    api(`/api/voorstel?${q}`).then((v) => setForm((f) => ({
      ...f,
      brandstof: v.brandstof ?? f.brandstof,
      transmissie: v.transmissie ?? f.transmissie,
    }))).catch(() => {})
  }, [form.merk, form.model])

  const zet = (veld) => (e) => setForm((f) => ({ ...f, [veld]: e.target.value }))

  function kiesMerk(e) {
    const merk = e.target.value
    setForm((f) => ({ ...f, merk, model: [...opties.modellen[merk]].sort()[0] }))
  }

  async function voorspel(e) {
    e.preventDefault()
    setBezig(true)
    setFout(null)
    try {
      const body = {
        merk: form.merk,
        model: form.model,
        bouwjaar: Number(form.bouwjaar),
        km: Number(form.km),
        km_verkoop: Number(form.km_verkoop),
        verkoop_maanden: verkoopMaanden,
        brandstof: form.brandstof,
        transmissie: form.transmissie,
        inflatie: Number(form.inflatie) / 100,
      }
      const r = await api('/api/voorspel', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })
      setResultaat({ ...r, auto: { ...form } })
    } catch (err) {
      setFout(err.message)
    } finally {
      setBezig(false)
    }
  }

  const modellen = opties ? [...(opties.modellen[form.merk] ?? [])].sort() : []
  const bouwjaren = opties
    ? Array.from({ length: opties.bouwjaar.max - opties.bouwjaar.min + 1 }, (_, i) => opties.bouwjaar.max - i)
    : []

  return (
    <>
      <header className="balk">
        <div className="balk-inhoud">
          <span className="logo" aria-hidden="true" />
          <span className="naam">Auto-Voorspeller</span>
          <span className="balk-sub">restwaarde van je occasion</span>
        </div>
      </header>

      <div className="pagina">
        <form className="paneel" onSubmit={voorspel}>
          <fieldset>
            <legend>Auto</legend>
            <div className="rij">
              <label>Merk
                <select value={form.merk} onChange={kiesMerk} disabled={!opties}>
                  {opties && Object.keys(opties.modellen).sort().map((m) => <option key={m}>{m}</option>)}
                </select>
              </label>
              <label>Model
                <select value={form.model} onChange={zet('model')} disabled={!opties}>
                  {modellen.map((m) => <option key={m}>{m}</option>)}
                </select>
              </label>
            </div>
            <div className="rij">
              <label>Bouwjaar
                <select value={form.bouwjaar} onChange={zet('bouwjaar')} disabled={!opties}>
                  {bouwjaren.map((j) => <option key={j}>{j}</option>)}
                </select>
              </label>
              <label>Brandstof
                <select value={form.brandstof} onChange={zet('brandstof')}>
                  {Object.entries(BRANDSTOF).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </div>
            <div className="rij">
              <label>Transmissie
                <select value={form.transmissie} onChange={zet('transmissie')}>
                  {Object.entries(TRANSMISSIE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label>Km-stand nu
                <input type="number" min="0" max="600000" step="1000" value={form.km} onChange={zet('km')} required />
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>Verkoop</legend>
            <div className="rij">
              <label>Moment
                <input type="month" value={form.verkoop} onChange={zet('verkoop')} required disabled={!opties}
                  min={opties ? plusMaanden(opties.nu, 1) : undefined}
                  max={opties ? plusMaanden(opties.nu, 12 * opties.max_jaren) : undefined} />
              </label>
              <label>
                <span>Km-stand {!kmVerkoopZelf && <em>({getal(KM_PER_JAAR)}/jaar)</em>}</span>
                <input type="number" min={form.km} max="700000" step="1000" value={form.km_verkoop} required
                  onChange={(e) => { setKmVerkoopZelf(true); zet('km_verkoop')(e) }} />
              </label>
            </div>
            <details>
              <summary>Inflatie meerekenen</summary>
              <label>Per jaar (%)
                <input type="number" min="0" max="20" step="0.5" value={form.inflatie} onChange={zet('inflatie')} />
              </label>
            </details>
          </fieldset>

          <button type="submit" disabled={!opties || bezig}>{bezig ? 'Rekenen' : 'Bereken'}</button>
          {fout && <p className="fout">{fout}</p>}
        </form>

        <main className="uitkomst">
          {resultaat ? <Resultaat r={resultaat} /> : (
            <p className="leeg">Kies een auto en een verkoopmoment.</p>
          )}
        </main>
      </div>

      <footer>
        Bron: AutoScout24-advertenties 2023–2026 en CBS. Vraagprijzen, geen transactieprijzen.
        Getoetst tot 2 jaar vooruit; verder is een schatting.
      </footer>
    </>
  )
}

function Resultaat({ r }) {
  const nu = r.punten[0]
  const verkoop = r.punten[r.punten.length - 1]
  const verlies = nu.midden - verkoop.midden
  const data = r.punten.map((x) => ({ ...x, label: maandNaam(x.datum), band: [x.laag, x.hoog] }))
  const { merk, model, bouwjaar } = r.auto

  return (
    <>
      <p className="auto-naam">{merk} {model}, {bouwjaar}</p>
      <h1 className="hoofdgetal">
        <span>Vraagprijs {maandNaam(verkoop.datum)}</span>
        {euro(verkoop.midden)}
      </h1>
      <p className="marge">tussen {euro(verkoop.laag)} en {euro(verkoop.hoog)}</p>

      <dl className="cijfers">
        <div><dt>Nu</dt><dd>{euro(nu.midden)}</dd></div>
        <div><dt>Waardeverlies</dt><dd>{euro(verlies)} <small>{Math.round((verlies / nu.midden) * 100)}%</small></dd></div>
        <div><dt>Km bij verkoop</dt><dd>{getal(verkoop.km)}</dd></div>
      </dl>

      {r.vergelijkbaar && (
        <p className="vergelijk">
          Nu te koop: {r.vergelijkbaar.aantal} vergelijkbare advertenties, mediaan {euro(r.vergelijkbaar.mediaan_prijs)} bij{' '}
          {getal(r.vergelijkbaar.mediaan_km)} km.
          {Math.abs(r.vergelijkbaar.correctie) >= 0.005 && <> Model daarop {r.vergelijkbaar.correctie > 0 ? 'opgehoogd' : 'verlaagd'} met{' '}
            {Math.abs(Math.round(r.vergelijkbaar.correctie * 100))}%.</>}
        </p>
      )}

      {!r.bekend_model && <p className="waarschuwing">Weinig data voor dit model; neem de uitkomst met een korrel zout.</p>}

      <div className="grafiek">
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid stroke="var(--lijn)" vertical={false} />
            <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: 'var(--lijn)' }} tick={{ fill: 'var(--zacht)' }} />
            <YAxis tickFormatter={(v) => `€${(v / 1000).toLocaleString('nl-NL', { maximumFractionDigits: 1 })}k`}
              tickLine={false} axisLine={false} width={52} domain={['auto', 'auto']} tick={{ fill: 'var(--zacht)' }} />
            <Tooltip formatter={(v, naam) => (naam === 'band' ? [`${euro(v[0])} – ${euro(v[1])}`, 'Marge']
              : [euro(v), 'Verwacht'])} />
            <Area dataKey="band" stroke="none" fill="var(--accent)" fillOpacity={0.12} isAnimationActive={false} />
            <Line dataKey="midden" stroke="var(--accent)" strokeWidth={2} dot={{ r: 3 }} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <table>
        <thead>
          <tr><th>Moment</th><th>Km</th><th>Laag</th><th>Verwacht</th><th>Hoog</th></tr>
        </thead>
        <tbody>
          {data.map((x) => (
            <tr key={x.datum}>
              <td>{x.maanden === 0 ? 'Nu' : x.label}</td><td>{getal(x.km)}</td><td>{euro(x.laag)}</td>
              <td>{euro(x.midden)}</td><td>{euro(x.hoog)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="toelichting">
        Euro&apos;s van {r.euro_van}. Uitgegaan van een nieuwprijs van {euro(r.nieuwprijs)}.
      </p>
    </>
  )
}
