export const meta = {
  name: 'squire-build',
  description: 'squire: index a structured spec, build it with one test-first builder, verify every requirement against the code, fix only the listed gaps, repeat until clean or out of rounds, report.',
  whenToUse: 'Launched by /squire:build with the parsed arguments. Not run directly.',
  phases: [
    { title: 'Index', detail: 'clean tree, spec indexed by requirement ID, check commands and their result at the base commit' },
    { title: 'Build', detail: 'one builder, test-first, from the spec' },
    { title: 'Verify', detail: 'spec and code only: a verdict per requirement with file:line evidence, the checks run in code' },
    { title: 'Fix', detail: 'only the gaps the round listed' },
    { title: 'Report', detail: 'verdict per requirement, open gaps, rounds' },
  ],
}

// A Workflow script has no filesystem, so each code step is a `squire` command that a low-effort clerk runs and copies back.
const A = args || {}
const PLUGIN = A.plugin_root, ROOT = A.project_root, SPEC = A.spec, RUN = A.run
if (!PLUGIN || !ROOT || !SPEC || !RUN) return { status: 'error', message: 'squire-build needs args.plugin_root, args.project_root, args.spec and args.run; launch it with /squire:build' }
const MAX_ROUNDS = Number.isInteger(A.max_rounds) && A.max_rounds >= 0 && A.max_rounds <= 5 ? A.max_rounds : 3
const TIMEOUT = Number.isInteger(A.timeout) && A.timeout >= 10 ? A.timeout : 300
const q = s => `'${String(s).replace(/'/g, `'\\''`)}'`
const SQUIRE = `${q(`${PLUGIN}/scripts/squire`)} --root ${q(ROOT)}`, RR = `--run ${q(RUN)}`

const timeline = [], concerns = [], calls = { total: 0, by: {} }
const note = m => { timeline.push(m); log(m) }, concern = m => { concerns.push(m); note(`concern: ${m}`) }
let RDIR = '', R = 0
const result = (status, message, extra) => ({ status, message, run: RUN, run_dir: RDIR, rounds: R, agent_calls: calls, concerns, timeline, ...(extra || {}) })

const call = (kind, prompt, opts) => { calls.total++; calls.by[kind] = (calls.by[kind] || 0) + 1; return agent(prompt, opts) }
// A builder or fixer that dies does not end the run: the next verification sees what it left.
const soft = async (kind, prompt, opts) => { try { return await call(kind, prompt, opts) } catch (e) { concern(`${opts.label} failed: ${e && e.message ? e.message : e}`); return null } }
const str = d => ({ type: 'string', description: d }), strs = d => ({ type: 'array', items: { type: 'string' }, description: d })
const obj = props => ({ type: 'object', properties: props, required: Object.keys(props) })
const LINE = obj({ output: str('the JSON line the command printed, copied exactly') })
const BUILDER = obj({ status: { type: 'string', enum: ['complete', 'blocked'] }, commits: strs('commit hashes'), tests_added: strs('test files or names'), notes: str('one or two sentences') })
const VERIFIER = obj({ file: str('the verifier file you wrote'), met: { type: 'integer' }, not_met: strs('requirement IDs not MET') })
const FIXER = obj({ fixed: strs('gap IDs fixed'), disputed: strs('gap IDs you believe are wrong, each with the reason'), commits: strs('commit hashes') })

class Stop { constructor(status, message) { this.status = status; this.message = message } }
const clerk = async (label, ph, command) => {
  const r = await call('clerk', `Run this one command with the Bash tool, with the tool's timeout set to 600000, and report what it prints. Do nothing else: do not edit files, fix anything or interpret the result.

    ${SQUIRE} ${command}

Put the last line it prints, exactly as printed, in output.`, { label: `clerk:${label}`, phase: ph, schema: LINE, effort: 'low' })
  let out
  try { out = JSON.parse(String(r && r.output).trim()) } catch (e) { throw new Stop('error', `${label}: the command printed no JSON: ${String(r && r.output).slice(0, 300)}`) }
  if (out.ok === false) throw new Stop(out.stop ? 'stopped' : 'error', `${label}: ${out.stop || out.error}`)
  return out
}

const ctx = st => `Project root: ${ROOT}
Spec: ${RDIR}/spec.md
Requirement index (every ID, its text and acceptance criteria): ${RDIR}/index.json
Base commit: ${st.base}; branch ${st.branch}
Project checks: ${st.commands.length ? st.commands.map(c => `\`${c}\``).join(', ') : 'none detected'}`
const drift = `Build only what the spec asks for. No feature, flag, option, endpoint, config key or abstraction the spec does not require; no requirement IDs in production code or its comments (tests may name them). squire checks both in code.`

const verify = async (st, rnd, retry) => soft('verifier', `${retry ? `Your verifier file for round ${rnd} was refused. Fix every one of these and write it again:\n${retry.map(e => `- ${e}`).join('\n')}\n\n` : ''}Verify round ${rnd} of a build against its spec.
${ctx(st)}
The code this build added or changed: git diff ${st.base}..HEAD
Run the project checks first, in code, and read the file it names: ${SQUIRE} check ${RR} --round ${rnd}
Write your verdicts to ${RDIR}/verify/verify-r${rnd}.json.`, { label: `verify:r${rnd}${retry ? ':retry' : ''}`, phase: 'Verify', agentType: 'squire:verifier', effort: 'high', schema: VERIFIER })

try {
  phase('Index')
  const st = await clerk('init', 'Index', `init --spec ${q(SPEC)} ${RR} --max-rounds ${MAX_ROUNDS} --timeout ${TIMEOUT}${(A.checks || []).map(c => ` --check ${q(c)}`).join('')}`)
  RDIR = st.run_dir
  ;(st.warnings || []).forEach(concern)
  note(`run ${RUN}: ${st.ids.length} requirements on ${st.branch} from ${String(st.base).slice(0, 10)}`)

  phase('Build')
  const b = await soft('builder', `Build this spec, test-first. The spec is your brief.
${ctx(st)}
${drift}
Commit as you go with plain git, staging files by name. Leave nothing uncommitted.`, { label: 'build', phase: 'Build', agentType: 'squire:builder', model: 'opus', schema: BUILDER })
  if (!b || b.status !== 'complete') concern(`the builder reported ${b ? b.status : 'nothing'}${b && b.notes ? `: ${b.notes}` : ''}`)

  let g = null
  for (R = 1; ; R++) {
    phase('Verify')
    await verify(st, R)
    g = await clerk(`gaps:r${R}`, 'Verify', `gaps ${RR} --round ${R}`)
    if (!g.valid) {
      await verify(st, R, g.errors)
      g = await clerk(`gaps:r${R}:retry`, 'Verify', `gaps ${RR} --round ${R}`)
      if (!g.valid) { concern(`the verifier file for round ${R} was refused twice: ${g.errors.slice(0, 5).join('; ')}`); break }
    }
    note(`round ${R}: ${g.open} open gaps ${JSON.stringify(g.by_kind)}`)
    if (!g.open) break
    if (R > MAX_ROUNDS) { concern(`gaps still open after ${MAX_ROUNDS} fix rounds: ${g.open}`); break }

    phase('Fix')
    const f = await soft('fixer', `Fix every gap in ${g.file}, and nothing else.
${ctx(st)}
${drift}
A gap of kind "unrequested" or "id-in-code" is fixed by removing what it names, not by adding a requirement for it. Commit with plain git, staging files by name.`, { label: `fix:r${R}`, phase: 'Fix', agentType: 'squire:fixer', model: 'opus', schema: FIXER })
    if (f && f.disputed && f.disputed.length) concern(`round ${R}: the fixer disputed ${f.disputed.join('; ')}`)
  }

  phase('Report')
  const rep = await clerk('report', 'Report', `report ${RR}`)
  const c = rep.counts
  const status = g && g.valid === false ? 'unverified' : rep.status
  return result(status, `${c.MET} met, ${c.PARTIAL} partial, ${c.MISSING} missing, ${c.WRONG} wrong, ${c['NOT CHECKED']} not checked; ${rep.open.length} open gaps after ${rep.rounds} verification rounds; ${calls.total} agent calls`,
    { report: rep.report, counts: c, open: rep.open })
} catch (e) {
  if (e instanceof Stop) return result(e.status, e.message)
  throw e
}
