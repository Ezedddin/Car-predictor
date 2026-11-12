import assert from 'node:assert/strict'
import test from 'node:test'
import { pasVoorstelToe } from '../src/voorstel.js'

const auto = { merk: 'Audi', model: 'A3', brandstof: 'petrol', transmissie: 'manual' }
const voorstel = { brandstof: 'diesel', transmissie: 'automatic' }

test('een voorstel voor een andere auto verandert niets', () => {
  assert.equal(pasVoorstelToe(auto, 'BMW', 'A3', voorstel, new Set()), auto)
  assert.equal(pasVoorstelToe(auto, 'Audi', 'A4', voorstel, new Set()), auto)
})

test('een voorstel behoudt de handmatige brandstofkeuze', () => {
  assert.deepEqual(
    pasVoorstelToe(auto, 'Audi', 'A3', voorstel, new Set(['brandstof'])),
    { ...auto, transmissie: 'automatic' },
  )
})

test('een ontbrekend voorstel behoudt de huidige keuze', () => {
  assert.deepEqual(pasVoorstelToe(auto, 'Audi', 'A3', {}, new Set()), auto)
})
