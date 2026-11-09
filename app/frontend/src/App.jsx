import { useEffect, useState } from 'react'
import {
  Area, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts'

const BRANDSTOF = {
  petrol: 'Benzine', diesel: 'Diesel', hybrid: 'Hybride', electric: 'Elektrisch', lpg: 'LPG', other: 'Overig',
}
const TRANSMISSIE = { manual: 'Handgeschakeld', automatic: 'Automaat', other: 'Overig' }
const KLEUR = ['var(--accent)', 'var(--accent-2)']

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

// Zolang de gebruiker de km-stand bij verkoop niet zelf invult, rekenen we hem uit (15.000 km per jaar)
const kmBijVerkoop = (auto, maanden) => (auto.kmZelf
  ? Number(auto.km_verkoop)
  : Number(auto.km) + Math.round((KM_PER_JAAR * maanden) / 12 / 1000) * 1000)

async function api(pad, opties) {
  const res = await fetch(pad, opties)
  const body = await res.json()
  if (!res.ok) {
    const detail = Array.isArray(body.detail) ? body.detail.map((d) => d.msg).join(', ') : body.detail
    throw new Error(detail || `Fout ${res.status}`)
  }
  return body
}

const STARTAUTO = {
  merk: 'Volkswagen', model: 'Golf', bouwjaar: 2020, brandstof: 'petrol', transmissie: 'manual',
  km: 90000, km_verkoop: 105000, kmZelf: false,
}

export default function App() {
  const [opties, setOpties] = useState(null)
  const [autos, setAutos] = useState([STARTAUTO])
  const [actief, setActief] = useState(0)
  const [verkoop, setVerkoop] = useState('')
  const [inflatie, setInflatie] = useState(0)
  const [resultaat, setResultaat] = useState(null)
  const [fout, setFout] = useState(null)
  const [bezig, setBezig] = useState(false)

  const verkoopMaanden = opties && verkoop ? maandenTussen(opties.nu, verkoop) : 12
  const auto = autos[actief]

  const wijzig = (i, velden) => setAutos((a) => a.map((x, j) => (j === i ? { ...x, ...velden } : x)))

  // Meest voorkomende brandstof en transmissie als standaard voor een gekozen model
  function stelVoor(i, merk, model) {
    const q = new URLSearchParams({ merk, model })
    api(`/api/voorstel?${q}`).then((v) => setAutos((a) => a.map((x, j) => (j === i && x.model === model ? {
      ...x, brandstof: v.brandstof ?? x.brandstof, transmissie: v.transmissie ?? x.transmissie,
    } : x)))).catch(() => {})
  }

  useEffect(() => {
    api('/api/opties').then((o) => {
      setOpties(o)
      setVerkoop(plusMaanden(o.nu, 12))
      stelVoor(0, STARTAUTO.merk, STARTAUTO.model)
    }).catch(() => setFout('Geen verbinding met de server (app/api).'))
  }, [])

  const zet = (veld) => (e) => wijzig(actief, { [veld]: e.target.value })

  function kiesMerk(e) {
    const merk = e.target.value
    const model = [...opties.modellen[merk]].sort()[0]
    wijzig(actief, { merk, model })
    stelVoor(actief, merk, model)
  }

  function kiesModel(e) {
    wijzig(actief, { model: e.target.value })
    stelVoor(actief, auto.merk, e.target.value)
  }

  function voegToe() {
    setAutos((a) => [a[0], { ...a[0] }])
    setActief(1)
  }

  function verwijder() {
    setAutos((a) => [a[0]])
    setActief(0)
  }

  async function voorspel(e) {
    e.preventDefault()
    setBezig(true)
    setFout(null)
    try {
      const uitkomsten = await Promise.all(autos.map((a) => api('/api/voorspel', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          merk: a.merk,
          model: a.model,
          bouwjaar: Number(a.bouwjaar),
          km: Number(a.km),
          km_verkoop: kmBijVerkoop(a, verkoopMaanden),
          verkoop_maanden: verkoopMaanden,
          brandstof: a.brandstof,
          transmissie: a.transmissie,
          inflatie: Number(inflatie) / 100,
        }),
      }).then((r) => ({ ...r, auto: { ...a } }))))
      setResultaat(uitkomsten)
    } catch (err) {
      setFout(err.message)
    } finally {
      setBezig(false)
    }
  }

  const modellen = opties ? [...(opties.modellen[auto.merk] ?? [])].sort() : []
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
          <div className="tabs" role="tablist">
            {autos.map((a, i) => (
              <button key={i} type="button" role="tab" aria-selected={i === actief}
                className={i === actief ? 'tab actief' : 'tab'} onClick={() => setActief(i)}>
                <span className="stip" style={{ background: KLEUR[i] }} />Auto {i + 1}
              </button>
            ))}
            {autos.length === 1
              ? <button type="button" className="tab toevoegen" onClick={voegToe}>+ Vergelijk</button>
              : <button type="button" className="tab toevoegen" onClick={verwijder}>Auto 2 weghalen</button>}
          </div>

          <fieldset>
            <legend>Auto {autos.length > 1 ? actief + 1 : ''}</legend>
            <div className="rij">
              <label>Merk
                <select value={auto.merk} onChange={kiesMerk} disabled={!opties}>
                  {opties && Object.keys(opties.modellen).sort().map((m) => <option key={m}>{m}</option>)}
                </select>
              </label>
              <label>Model
                <select value={auto.model} onChange={kiesModel} disabled={!opties}>
                  {modellen.map((m) => <option key={m}>{m}</option>)}
                </select>
              </label>
            </div>
            <div className="rij">
              <label>Bouwjaar
                <select value={auto.bouwjaar} onChange={zet('bouwjaar')} disabled={!opties}>
                  {bouwjaren.map((j) => <option key={j}>{j}</option>)}
                </select>
              </label>
              <label>Brandstof
                <select value={auto.brandstof} onChange={zet('brandstof')}>
                  {Object.entries(BRANDSTOF).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
            </div>
            <div className="rij">
              <label>Transmissie
                <select value={auto.transmissie} onChange={zet('transmissie')}>
                  {Object.entries(TRANSMISSIE).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select>
              </label>
              <label>Km-stand nu
                <input type="number" min="0" max="600000" step="1000" value={auto.km} onChange={zet('km')} required />
              </label>
            </div>
          </fieldset>

          <fieldset>
            <legend>Verkoop</legend>
            <div className="rij">
              <label>Moment
                <input type="month" value={verkoop} onChange={(e) => setVerkoop(e.target.value)} required disabled={!opties}
                  min={opties ? plusMaanden(opties.nu, 1) : undefined}
                  max={opties ? plusMaanden(opties.nu, 12 * opties.max_jaren) : undefined} />
              </label>
              <label>
                <span>Km-stand {!auto.kmZelf && <em>({getal(KM_PER_JAAR)}/jaar)</em>}</span>
                <input type="number" min={auto.km} max="700000" step="1000" value={kmBijVerkoop(auto, verkoopMaanden)} required
                  onChange={(e) => wijzig(actief, { kmZelf: true, km_verkoop: e.target.value })} />
              </label>
            </div>
            <details>
              <summary>Inflatie meerekenen</summary>
              <label>Per jaar (%)
                <input type="number" min="0" max="20" step="0.5" value={inflatie} onChange={(e) => setInflatie(e.target.value)} />
              </label>
            </details>
          </fieldset>

          <button type="submit" className="bereken" disabled={!opties || bezig}>
            {bezig ? 'Rekenen' : autos.length > 1 ? 'Vergelijk' : 'Bereken'}
          </button>
          {fout && <p className="fout">{fout}</p>}
        </form>

        <main className="uitkomst">
          {!resultaat && <p className="leeg">Kies een auto en een verkoopmoment.</p>}
          {resultaat?.length === 1 && <Resultaat r={resultaat[0]} />}
          {resultaat?.length === 2 && <Vergelijking rs={resultaat} />}
        </main>
      </div>

      <footer>
        Bron: AutoScout24-advertenties 2023–2026 en CBS. Vraagprijzen, geen transactieprijzen.
        Getoetst tot 2 jaar vooruit; verder is een schatting.
      </footer>
    </>
  )
}

const naamVan = ({ merk, model, bouwjaar }) => `${merk} ${model}, ${bouwjaar}`
const kortVan = ({ model, bouwjaar }) => `${model} ${bouwjaar}`

// Eén lijn met marge per auto; de punten vallen op dezelfde maanden omdat het verkoopmoment gedeeld is
function Grafiek({ rs, namen }) {
  const data = rs[0].punten.map((x, i) => {
    const rij = { label: maandNaam(x.datum) }
    rs.forEach((r, j) => {
      rij[`midden${j}`] = r.punten[i].midden
      rij[`band${j}`] = [r.punten[i].laag, r.punten[i].hoog]
    })
    return rij
  })

  return (
    <div className="grafiek">
      <ResponsiveContainer width="100%" height={240}>
        <ComposedChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid stroke="var(--lijn)" vertical={false} />
          <XAxis dataKey="label" tickLine={false} axisLine={{ stroke: 'var(--lijn)' }} tick={{ fill: 'var(--zacht)' }} />
          <YAxis tickFormatter={(v) => `€${(v / 1000).toLocaleString('nl-NL', { maximumFractionDigits: 1 })}k`}
            tickLine={false} axisLine={false} width={52} domain={['auto', 'auto']} tick={{ fill: 'var(--zacht)' }} />
          <Tooltip formatter={(v, naam) => (Array.isArray(v) ? [`${euro(v[0])} – ${euro(v[1])}`, naam] : [euro(v), naam])} />
          {rs.map((_, j) => (
            <Area key={`b${j}`} dataKey={`band${j}`} name={`Marge ${namen[j]}`} stroke="none" fill={KLEUR[j]}
              fillOpacity={0.12} isAnimationActive={false} />
          ))}
          {rs.map((_, j) => (
            <Line key={`l${j}`} dataKey={`midden${j}`} name={namen[j]} stroke={KLEUR[j]} strokeWidth={2}
              dot={{ r: 3 }} isAnimationActive={false} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  )
}

function Resultaat({ r }) {
  const nu = r.punten[0]
  const verkoop = r.punten[r.punten.length - 1]
  const verlies = nu.midden - verkoop.midden

  return (
    <>
      <p className="auto-naam">{naamVan(r.auto)}</p>
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

      <Disclaimer rs={[r]} />
      <Vergelijkbaar r={r} />
      {!r.bekend_model && <p className="waarschuwing">Weinig data voor dit model; neem de uitkomst met een korrel zout.</p>}

      <Grafiek rs={[r]} namen={['Verwacht']} />

      <table>
        <thead>
          <tr><th>Moment</th><th>Km</th><th>Laag</th><th>Verwacht</th><th>Hoog</th></tr>
        </thead>
        <tbody>
          {r.punten.map((x) => (
            <tr key={x.datum}>
              <td>{x.maanden === 0 ? 'Nu' : maandNaam(x.datum)}</td><td>{getal(x.km)}</td><td>{euro(x.laag)}</td>
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

// Altijd zichtbaar; opvallender als een van de prijzen onder de € 10.000 zit, waar het model het minst goed is
function Disclaimer({ rs }) {
  const goedkoop = rs.some((r) => r.punten.some((p) => p.midden < 10000))
  return (
    <p className={goedkoop ? 'disclaimer let-op' : 'disclaimer'}>
      <strong>Dit is een schatting, geen taxatie.</strong> Voor goedkopere auto&apos;s onder de € 10.000 is deze
      voorspelling minder betrouwbaar.
    </p>
  )
}

function Vergelijkbaar({ r, naam }) {
  if (!r.vergelijkbaar) return null
  const v = r.vergelijkbaar
  const procent = Math.round(Math.abs(v.correctie) * 100)
  return (
    <p className="vergelijk">
      {naam && <>{naam}: </>}nu te koop: {v.aantal} vergelijkbare advertenties, mediaan {euro(v.mediaan_prijs)} bij{' '}
      {getal(v.mediaan_km)} km.
      {procent >= 1 && <> Model daarop {v.correctie > 0 ? 'opgehoogd' : 'verlaagd'} met {procent}%.</>}
    </p>
  )
}

function Vergelijking({ rs }) {
  // Zelfde model en bouwjaar? Dan nummeren, anders zijn de namen in de grafiek niet te onderscheiden
  const kort = rs.map((r) => kortVan(r.auto))
  const namen = kort[0] === kort[1] ? kort.map((k, i) => `${k} (${i + 1})`) : kort
  const laatste = rs.map((r) => r.punten[r.punten.length - 1])
  const verschil = laatste[0].midden - laatste[1].midden

  return (
    <>
      <p className="auto-naam">Vraagprijs {maandNaam(laatste[0].datum)}</p>
      <div className="duo">
        {rs.map((r, i) => {
          const nu = r.punten[0].midden
          const verlies = nu - laatste[i].midden
          return (
            <div key={i} className="duo-auto">
              <p className="duo-naam"><span className="stip" style={{ background: KLEUR[i] }} />{naamVan(r.auto)}</p>
              <p className="duo-prijs">{euro(laatste[i].midden)}</p>
              <p className="marge">tussen {euro(laatste[i].laag)} en {euro(laatste[i].hoog)}</p>
              <dl className="duo-cijfers">
                <dt>Nu</dt><dd>{euro(nu)}</dd>
                <dt>Waardeverlies</dt><dd>{euro(verlies)} <small>{Math.round((verlies / nu) * 100)}%</small></dd>
                <dt>Km bij verkoop</dt><dd>{getal(laatste[i].km)}</dd>
              </dl>
            </div>
          )
        })}
      </div>

      <p className="duo-verschil">
        {Math.abs(verschil) < 50 ? 'Bij verkoop zijn ze ongeveer evenveel waard.'
          : <>{verschil > 0 ? namen[0] : namen[1]} is bij verkoop {euro(Math.abs(verschil))} meer waard.</>}
      </p>

      <Disclaimer rs={rs} />
      {rs.map((r, i) => <Vergelijkbaar key={i} r={r} naam={namen[i]} />)}
      {rs.some((r) => !r.bekend_model) && (
        <p className="waarschuwing">Weinig data voor een van deze modellen; neem de uitkomst met een korrel zout.</p>
      )}

      <Grafiek rs={rs} namen={namen} />

      <table>
        <thead>
          <tr><th>Moment</th><th>{namen[0]}</th><th>{namen[1]}</th><th>Verschil</th></tr>
        </thead>
        <tbody>
          {rs[0].punten.map((x, i) => {
            const y = rs[1].punten[i]
            return (
              <tr key={x.datum}>
                <td>{x.maanden === 0 ? 'Nu' : maandNaam(x.datum)}</td>
                <td>{euro(x.midden)}</td><td>{euro(y.midden)}</td><td>{euro(x.midden - y.midden)}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <p className="toelichting">
        Euro&apos;s van {rs[0].euro_van}. Uitgegaan van een nieuwprijs van {euro(rs[0].nieuwprijs)} en{' '}
        {euro(rs[1].nieuwprijs)}.
      </p>
    </>
  )
}
