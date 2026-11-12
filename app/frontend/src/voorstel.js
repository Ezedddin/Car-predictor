export function pasVoorstelToe(auto, merk, model, voorstel, handmatig) {
  if (auto.merk !== merk || auto.model !== model) return auto
  return {
    ...auto,
    brandstof: handmatig.has('brandstof') ? auto.brandstof : (voorstel.brandstof ?? auto.brandstof),
    transmissie: handmatig.has('transmissie') ? auto.transmissie : (voorstel.transmissie ?? auto.transmissie),
  }
}
