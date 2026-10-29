// Fails the build when ko.json and en.json do not have the same keys.
import { readFileSync } from 'node:fs'

const load = (name) => JSON.parse(readFileSync(new URL(`../src/locales/${name}.json`, import.meta.url), 'utf8'))
const keys = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) => (typeof v === 'object' ? keys(v, `${prefix}${k}.`) : [`${prefix}${k}`]))

const ko = new Set(keys(load('ko')))
const en = new Set(keys(load('en')))
const onlyKo = [...ko].filter((k) => !en.has(k))
const onlyEn = [...en].filter((k) => !ko.has(k))
if (onlyKo.length || onlyEn.length) {
  console.error('Locale keys differ.\n  only in ko:', onlyKo, '\n  only in en:', onlyEn)
  process.exit(1)
}
console.log(`locales ok (${ko.size} keys)`)
