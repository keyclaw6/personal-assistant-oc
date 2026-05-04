#!/usr/bin/env node
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { fileURLToPath, pathToFileURL } from "node:url";
import { isRecallable, parseClaims } from "./memory-lib.mjs";
import { getMemory } from "./mem.mjs";
import { searchMemory } from "./memory-search.mjs";

const execFileAsync = promisify(execFile);
const memCliPath = fileURLToPath(new URL("./mem.mjs", import.meta.url));
const searchCliPath = fileURLToPath(new URL("./memory-search.mjs", import.meta.url));

const cases = [
  {
    name: "file memory without vector database",
    query: "file based memory no vector database",
    expected: ["preference.memory.no-vector-db", "concept.file-based-memory", "entity.personal-assistant-oc.file-memory"],
    topK: 8
  },
  {
    name: "progressive retrieval index first",
    query: "progressive disclosure index first retrieval",
    expected: ["decision.progressive-disclosure", "synthesis.memory.index-first", "concept.file-memory.progressive"],
    topK: 5
  },
  {
    name: "timezone",
    query: "Kristian timezone Europe Copenhagen",
    expected: ["profile.kristian.timezone", "profile.kristian"],
    topK: 5
  },
  {
    name: "memory maintenance node scripts",
    query: "dependency free node scripts memory maintenance",
    expected: ["stack.memory.node-scripts", "stack.local-openclaw"],
    topK: 5
  },
  {
    name: "no lexical match returns no memory",
    query: "zzzznotfoundterm",
    expected: [],
    expectNoResults: true,
    topK: 5
  },
  {
    name: "retired memory excluded by default",
    query: "retiredsentinel deprecatedsentinel obsoletesentinel",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.retired"],
    topK: 5,
    fixtures: [
      {
        kind: "page",
        id: "eval.retired",
        title: "Retired Eval",
        path: "eval/retired.md",
        status: "retired",
        visibility: "local",
        confidence: 0.9,
        importance: "critical",
        tokenCost: 10,
        tags: ["retiredsentinel"],
        summary: "Retiredsentinel deprecatedsentinel obsoletesentinel memory.",
        body: "Retiredsentinel deprecatedsentinel obsoletesentinel memory."
      }
    ]
  },
  {
    name: "contested memory excluded by default",
    query: "contestedsentinel contradictionsentinel quarantinesentinel",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.contested"],
    topK: 5,
    fixtures: [
      {
        kind: "page",
        id: "eval.contested",
        title: "Contested Eval",
        path: "eval/contested.md",
        status: "contested",
        visibility: "local",
        confidence: 0.9,
        importance: "critical",
        tokenCost: 10,
        tags: ["contestedsentinel"],
        summary: "Contestedsentinel contradictionsentinel quarantinesentinel memory.",
        body: "Contestedsentinel contradictionsentinel quarantinesentinel memory."
      }
    ]
  },
  {
    name: "private memory excluded by default",
    query: "privatesentinel hiddensentinel quarantinesentinel",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.private"],
    topK: 5,
    fixtures: [
      {
        kind: "page",
        id: "eval.private",
        title: "Private Eval",
        path: "eval/private.md",
        status: "active",
        visibility: "private",
        confidence: 0.9,
        importance: "critical",
        tokenCost: 10,
        tags: ["privatesentinel"],
        summary: "Privatesentinel hiddensentinel quarantinesentinel memory.",
        body: "Privatesentinel hiddensentinel quarantinesentinel memory."
      }
    ]
  },
  {
    name: "claim under contested page excluded by default",
    query: "nestedcontestedsentinel claimneedle",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.nested-contested-claim"],
    topK: 5,
    fixtures: [
      {
        kind: "claim",
        id: "eval.nested-contested-claim",
        title: "Nested Contested Claim",
        pageTitle: "Nested Contested Claim",
        path: "eval/nested-contested.md",
        status: "active",
        parentStatus: "contested",
        visibility: "local",
        parentVisibility: "local",
        confidence: 0.99,
        importance: "critical",
        tokenCost: 10,
        text: "Nestedcontestedsentinel claimneedle should not recall."
      }
    ]
  },
  {
    name: "claim under private page excluded by default",
    query: "nestedprivatesentinel claimneedle",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.nested-private-claim"],
    topK: 5,
    fixtures: [
      {
        kind: "claim",
        id: "eval.nested-private-claim",
        title: "Nested Private Claim",
        pageTitle: "Nested Private Claim",
        path: "eval/nested-private.md",
        status: "active",
        parentStatus: "active",
        visibility: "local",
        parentVisibility: "private",
        confidence: 0.99,
        importance: "critical",
        tokenCost: 10,
        text: "Nestedprivatesentinel claimneedle should not recall."
      }
    ]
  },
  {
    name: "private block text is not searchable",
    query: "secretneedle",
    expected: [],
    expectNoResults: true,
    forbidden: ["eval.private-block"],
    topK: 5,
    fixtures: [
      {
        kind: "page",
        id: "eval.private-block",
        title: "Private Block Eval",
        path: "eval/private-block.md",
        status: "active",
        visibility: "local",
        confidence: 0.99,
        importance: "critical",
        tokenCost: 10,
        tags: [],
        summary: "<private>secretneedle should not print</private>",
        body: "[private omitted]"
      }
    ]
  }
];

function runParserEval() {
  const body = [
    "## Claims",
    "",
    "| ID | Status | Confidence | Evidence | Claim |",
    "| --- | --- | ---: | --- | --- |",
    "| eval.public-claim | active | 0.8 | public evidence | Public claim text. |",
    "<private>",
    "| eval.private-claim | active | 0.99 | secretneedle evidence | secretneedle private claim text |",
    "</private>",
    "| eval.inline-private | active | 0.8 | <private>hidden evidence</private> | Inline <private>hidden claim</private> text. |"
  ].join("\n");
  const claims = parseClaims(body, {
    id: "eval.claim-parser",
    title: "Claim Parser Eval",
    path: "eval/claim-parser.md",
    status: "active",
    visibility: "local"
  });
  const serialized = JSON.stringify(claims);
  return {
    name: "private claim parser sanitization",
    passed: claims.some((claim) => claim.id === "eval.public-claim")
      && !claims.some((claim) => claim.id === "eval.private-claim")
      && !serialized.includes("secretneedle")
      && !serialized.includes("hidden evidence")
      && !serialized.includes("hidden claim"),
    details: claims.map((claim) => claim.id).join(", ") || "(none)"
  };
}

function runReportRecallabilityEval() {
  const body = [
    "## Claims",
    "",
    "| ID | Status | Confidence | Evidence | Claim |",
    "| --- | --- | ---: | --- | --- |",
    "| eval.private-report-claim | active | 0.99 | reportsentinel evidence | reportsentinel private report claim |"
  ].join("\n");
  const claims = parseClaims(body, {
    id: "eval.private-report-page",
    title: "Private Report Page",
    path: "eval/private-report.md",
    relativePath: "eval/private-report.md",
    status: "active",
    visibility: "private"
  });
  const reportableClaims = claims.filter((claim) => isRecallable(claim, {
    includeContested: true,
    includeRetired: true,
    includePrivate: false
  }));
  return {
    name: "private claims excluded from reportable claim output",
    passed: claims.length === 1 && reportableClaims.length === 0,
    details: `claims=${claims.length}, reportable=${reportableClaims.length}`
  };
}

async function runFacadeCliEvals() {
  const evals = [];

  const fixtureSearch = await searchMemory("alpha beta gamma", {
    limit: 2,
    fixtureOnly: true,
    fixtures: [
      {
        kind: "page",
        id: "eval.partial-critical",
        title: "Alpha Memory",
        path: "eval/partial-critical.md",
        status: "active",
        visibility: "local",
        confidence: 1,
        importance: "critical",
        tokenCost: 5,
        tags: ["alpha"],
        summary: "Alpha memory repeated alpha repeated alpha repeated alpha.",
        body: "Alpha memory repeated alpha repeated alpha repeated alpha."
      },
      {
        kind: "page",
        id: "eval.full-coverage",
        title: "Alpha Beta Gamma",
        path: "eval/full-coverage.md",
        status: "active",
        visibility: "local",
        confidence: 0.7,
        importance: "low",
        tokenCost: 5,
        tags: [],
        summary: "Alpha beta gamma.",
        body: "Alpha beta gamma."
      }
    ]
  });
  evals.push({
    name: "search ranks full query coverage above boosted partial matches",
    passed: fixtureSearch.results[0]?.id === "eval.full-coverage",
    details: fixtureSearch.results.map((result) => `${result.id}:${result.coverage}/${result.termCount}`).join(", ") || "(none)"
  });

  const memJson = await execFileAsync(process.execPath, [
    memCliPath,
    "search",
    "agent memory facade",
    "--limit=1",
    "--format=json"
  ], { maxBuffer: 1024 * 1024 });
  const memOutput = JSON.parse(memJson.stdout);
  evals.push({
    name: "mem facade supports --flag=value JSON output",
    passed: memOutput.results.length === 1 && memOutput.results[0]?.coverage >= 1,
    details: `results=${memOutput.results.length}`
  });

  const directMd = await execFileAsync(process.execPath, [
    searchCliPath,
    "--query=agent memory facade",
    "--limit=1",
    "--format=md"
  ], { maxBuffer: 1024 * 1024 });
  evals.push({
    name: "direct search supports --flag=value Markdown output",
    passed: directMd.stdout.includes("| Rank | Score | Match | Status | Conf |"),
    details: directMd.stdout.split(/\r?\n/).find((line) => line.startsWith("| Rank |")) || "(missing header)"
  });

  const zeroLimit = await execFileAsync(process.execPath, [
    memCliPath,
    "search",
    "agent memory facade",
    "--limit=0",
    "--format=json"
  ], { maxBuffer: 1024 * 1024 });
  const zeroOutput = JSON.parse(zeroLimit.stdout);
  evals.push({
    name: "mem facade honors --limit=0",
    passed: zeroOutput.results.length === 0,
    details: `results=${zeroOutput.results.length}`
  });

  const directFalsePrivate = await execFileAsync(process.execPath, [
    searchCliPath,
    "--query=privatesentinel",
    "--include-private=false",
    "--format=json"
  ], { maxBuffer: 1024 * 1024 });
  const directFalseOutput = JSON.parse(directFalsePrivate.stdout);
  evals.push({
    name: "direct search treats --include-private=false as false",
    passed: directFalseOutput.results.length === 0,
    details: `results=${directFalseOutput.results.length}`
  });

  const facadeFalsePrivate = await execFileAsync(process.execPath, [
    memCliPath,
    "search",
    "privatesentinel",
    "--include-private=false",
    "--format=json"
  ], { maxBuffer: 1024 * 1024 });
  const facadeFalseOutput = JSON.parse(facadeFalsePrivate.stdout);
  evals.push({
    name: "mem facade treats --include-private=false as false",
    passed: facadeFalseOutput.results.length === 0,
    details: `results=${facadeFalseOutput.results.length}`
  });

  const facadeFalseContested = await execFileAsync(process.execPath, [
    memCliPath,
    "search",
    "contestedsentinel",
    "--include-contested=0",
    "--format=json"
  ], { maxBuffer: 1024 * 1024 });
  const facadeContestedOutput = JSON.parse(facadeFalseContested.stdout);
  evals.push({
    name: "mem facade treats --include-contested=0 as false",
    passed: facadeContestedOutput.results.length === 0,
    details: `results=${facadeContestedOutput.results.length}`
  });

  const noMatchMd = await execFileAsync(process.execPath, [
    memCliPath,
    "get",
    "agent memory facade missing target"
  ], { maxBuffer: 1024 * 1024 });
  evals.push({
    name: "mem get no-match suggestions render compact Markdown table",
    passed: noMatchMd.stdout.includes("| Rank | Kind | ID | Status | Conf | Path | Hint |")
      && !/\| \d+ \|[^\n]*\n[^\|#\s]/.test(noMatchMd.stdout),
    details: noMatchMd.stdout.split(/\r?\n/).find((line) => line.startsWith("| Rank |")) || "(missing header)"
  });

  return evals;
}

export async function runMemoryEval() {
  const failures = [];
  const results = [];

  for (const testCase of cases) {
    const output = await searchMemory(testCase.query, { limit: testCase.topK, fixtures: testCase.fixtures || [] });
    const topIds = output.results.map((result) => result.id);
    const hit = testCase.expected.length === 0 && !testCase.expectNoResults
      ? true
      : testCase.expected.length === 0
        ? topIds.length === 0
      : testCase.expected.some((id) => topIds.includes(id));
    const forbiddenHit = (testCase.forbidden || []).some((id) => topIds.includes(id));
    results.push({
      name: testCase.name,
      query: testCase.query,
      topK: testCase.topK,
      expected: testCase.expected,
      forbidden: testCase.forbidden || [],
      topIds,
      hit,
      forbiddenHit
    });
    if (!hit || forbiddenHit) failures.push(testCase.name);
  }

  const parserEval = runParserEval();
  if (!parserEval.passed) failures.push(parserEval.name);
  const reportRecallabilityEval = runReportRecallabilityEval();
  if (!reportRecallabilityEval.passed) failures.push(reportRecallabilityEval.name);

  const getPageEval = await getMemory("memory-wiki/syntheses/memory-architecture.md");
  const getClaimEval = await getMemory("synthesis.memory.short-facade");
  const getMissingEval = await getMemory("zzzznotfoundterm");
  const getEvals = [
    {
      name: "mem get resolves page paths",
      passed: getPageEval.item?.id === "synthesis.memory-architecture",
      details: getPageEval.item?.id || "(none)"
    },
    {
      name: "mem get resolves claim ids",
      passed: getClaimEval.item?.id === "synthesis.memory.short-facade",
      details: getClaimEval.item?.id || "(none)"
    },
    {
      name: "mem get missing target returns suggestions only",
      passed: !getMissingEval.item && Array.isArray(getMissingEval.suggestions),
      details: `item=${getMissingEval.item ? "yes" : "no"}, suggestions=${getMissingEval.suggestions.length}`
    }
  ];
  for (const result of getEvals) {
    if (!result.passed) failures.push(result.name);
  }
  const facadeCliEvals = await runFacadeCliEvals();
  for (const result of facadeCliEvals) {
    if (!result.passed) failures.push(result.name);
  }

  return { cases: results, parserEval, reportRecallabilityEval, getEvals, facadeCliEvals, failures };
}

async function main() {
  const output = await runMemoryEval();
  for (const result of output.cases) {
    const marker = result.hit ? "PASS" : "FAIL";
    console.log(`${marker} ${result.name}`);
    console.log(`  query: ${result.query}`);
    console.log(`  top ${result.topK}: ${result.topIds.join(", ") || "(none)"}`);
    if (result.forbidden.length) console.log(`  forbidden: ${result.forbidden.join(", ")}`);
  }
  console.log(`${output.parserEval.passed ? "PASS" : "FAIL"} ${output.parserEval.name}`);
  console.log(`  parsed claims: ${output.parserEval.details}`);
  console.log(`${output.reportRecallabilityEval.passed ? "PASS" : "FAIL"} ${output.reportRecallabilityEval.name}`);
  console.log(`  ${output.reportRecallabilityEval.details}`);
  for (const result of output.getEvals) {
    console.log(`${result.passed ? "PASS" : "FAIL"} ${result.name}`);
    console.log(`  ${result.details}`);
  }
  for (const result of output.facadeCliEvals) {
    console.log(`${result.passed ? "PASS" : "FAIL"} ${result.name}`);
    console.log(`  ${result.details}`);
  }

  if (output.failures.length > 0) {
    console.error(`Memory retrieval evaluation failed: ${output.failures.join(", ")}`);
    process.exit(1);
  }

  console.log(`Memory retrieval evaluation passed (${output.cases.length} cases).`);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch((error) => {
    console.error(error);
    process.exit(1);
  });
}
