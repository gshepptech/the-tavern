// Runs workflows/build.js against a scripted stand-in for the Workflow runtime,
// its agents and the `squire` commands the clerk runs, so the script's routing is
// tested without a session. The squire commands are covered by the Python tests;
// here each one answers from the scenario.
//
// usage: node workflow_harness.mjs <path to build.js> <scenario>
// prints one JSON object: {meta, result, phases, labels, prompts, options, commands, schemaProblems, syntaxFile}

import { readFileSync, writeFileSync, mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const [, , scriptPath, name] = process.argv
const source = readFileSync(scriptPath, 'utf8')

const metaMatch = source.match(/^export const meta = (\{[\s\S]*?\n\})\n/m)
if (!metaMatch) throw new Error('no `export const meta = {...}` literal at the top of the script')
const meta = Function(`return (${metaMatch[1]})`)()
const body = source.replace(/^export const meta = /m, 'const meta = ')
const syntaxFile = join(mkdtempSync(join(tmpdir(), 'squire-wf-')), 'wrapped.mjs')
writeFileSync(syntaxFile, `export default async function workflow(agent, parallel, pipeline, phase, log, args, budget, workflow) {\n${body}\n}\n`)
const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor
const fn = new AsyncFunction('agent', 'parallel', 'pipeline', 'phase', 'log', 'args', 'budget', 'workflow', body)

const schemaProblems = []
const checkSchema = (s, where) => {
  if (!s || typeof s !== 'object') return
  if (s.type === 'object') {
    const props = Object.keys(s.properties || {})
    for (const r of s.required || []) if (!props.includes(r)) schemaProblems.push(`${where}: required "${r}" not in properties`)
    for (const [k, v] of Object.entries(s.properties || {})) checkSchema(v, `${where}.${k}`)
  }
  if (s.enum && !s.enum.length) schemaProblems.push(`${where}: empty enum`)
  if (s.items) checkSchema(s.items, `${where}[]`)
}

// open: gaps open after each round's verification; invalid: rounds whose first verifier file is refused (twice if listed twice).
const SCENARIOS = {
  clean: { open: [0] },
  'fix-then-clean': { open: [2, 0] },
  'round-cap': { open: [3, 2, 1, 1] },
  'no-rounds': { open: [1], maxRounds: 0 },
  'refused-then-accepted': { open: [0], invalid: { 1: 1 } },
  'refused-twice': { open: [0], invalid: { 1: 2 } },
  'init-stop': { initStop: 'the working tree has uncommitted changes to tracked files; commit or stash them first' },
  'builder-dies': { open: [0], builderThrows: true },
  'custom-checks': { open: [0], checks: ['make test', "go test -run 'X'"] },
}
const sc = SCENARIOS[name]
if (!sc) throw new Error(`unknown scenario ${name}`)

const labels = [], phases = [], prompts = {}, options = {}, commands = []
const refusals = {}

const squire = (cmd, rest) => {
  const round = Number((rest.match(/--round (\d+)/) || [])[1] || 0)
  switch (cmd) {
    case 'init':
      return sc.initStop ? { ok: false, stop: sc.initStop } : { ok: true, run_dir: '/p/squire-runs/r', base: 'base0000000000', branch: 'squire/r',
        ids: ['R-001', 'R-002'], commands: ['make test'], baseline: { test: 0 }, warnings: ['R-002 has no acceptance criteria'] }
    case 'gaps': {
      refusals[round] = (refusals[round] || 0) + 1
      if (refusals[round] <= ((sc.invalid || {})[round] || 0)) return { ok: true, valid: false, errors: ['R-002: no verdict'] }
      const open = (sc.open || [])[round - 1] ?? 0
      return { ok: true, valid: true, open, by_kind: open ? { requirement: open } : {}, file: `/p/squire-runs/r/verify/gaps-r${round}.json` }
    }
    case 'report': {
      const last = (sc.open || [0])[(sc.open || [0]).length - 1]
      return { ok: true, status: last ? 'done_with_gaps' : 'done', counts: { MET: 2 - Math.min(last, 2), PARTIAL: Math.min(last, 2), MISSING: 0, WRONG: 0, 'NOT CHECKED': 0 },
        rounds: (sc.open || []).length, open: last ? ['G-1'] : [], report: '/p/squire-runs/r/report.md' }
    }
    default:
      throw new Error(`harness: no answer for squire ${cmd}`)
  }
}

const agent = async (prompt, opts = {}) => {
  const label = opts.label || '(unlabelled)'
  labels.push(label)
  prompts[label] = prompt
  options[label] = { agentType: opts.agentType || '', model: opts.model || '', effort: opts.effort || '', phase: opts.phase || '' }
  if (opts.schema) checkSchema(opts.schema, label)
  if (label.startsWith('clerk:')) {
    const line = prompt.split('\n').find(l => l.startsWith('    ')) || ''
    const m = line.match(/--root '[^']*' ([\w-]+)(.*)$/)
    commands.push(`${m[1]}${m[2]}`)
    return { output: JSON.stringify(squire(m[1], m[2])) }
  }
  if (label === 'build') {
    if (sc.builderThrows) throw new Error('agent crashed')
    return { status: 'complete', commits: ['abc'], tests_added: ['tests/test_x.py'], notes: 'secret builder notes' }
  }
  if (label.startsWith('verify:')) return { file: 'v.json', met: 2, not_met: [] }
  if (label.startsWith('fix:')) return { fixed: ['G-1'], disputed: label === 'fix:r1' ? ['G1-2: the spec does not ask for this'] : [], commits: ['def'] }
  throw new Error(`harness: unexpected agent ${label}`)
}
const parallel = async thunks => Promise.all(thunks.map(t => t().catch(() => null)))
const pipeline = async () => { throw new Error('pipeline is not used by this script') }
const phase = t => phases.push(t)
const log = () => {}

const result = await fn(agent, parallel, pipeline, phase, log, {
  plugin_root: '/plugin', project_root: '/p', spec: '/p/docs/spec.md', run: 'r', timeout: 300,
  max_rounds: sc.maxRounds ?? 3, checks: sc.checks || [],
}, { total: null, spent: () => 0, remaining: () => Infinity }, async () => { throw new Error('nested workflows unused') })

process.stdout.write(JSON.stringify({ meta, result, phases, labels, prompts, options, commands, schemaProblems, syntaxFile }))
