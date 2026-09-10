// English UI copy for the built-in agent catalog. The backend is fully
// English (LLMs and agents consume it directly); this map provides the
// user-facing names and descriptions, keyed by domain id and member id.
//
// Every domain in DOMAIN_CATALOG must appear here with an entry for each of its
// team members, or `test_domain_frontend_parity.py` fails — this file is the
// one place a new squad can be forgotten without the TypeScript build noticing,
// because the map is keyed by `string` rather than by `AgentDomain`. It is
// keyed loosely on purpose: a custom agent's `custom:{id}` selector is looked up
// here too and must miss rather than fail to type-check.

import type { AgentEvent, BuiltinAgent } from '@/types';

interface MemberLocale {
  name: string;
  description: string;
}

interface DomainLocale {
  name: string;
  description: string;
  capabilities: string[];
  team: Record<string, MemberLocale>;
}

export const AGENT_LOCALE: Record<string, DomainLocale> = {
  software: {
    name: 'Software Expert',
    description:
      'Expert in writing code, debugging, architectural design, and API development tasks.',
    capabilities: [
      'Code writing',
      'Debugging',
      'Architecture design',
      'Code review',
    ],
    team: {
      architect: {
        name: 'Architect',
        description: 'Defines the solution architecture and design decisions.',
      },
      coder: {
        name: 'Coder',
        description: 'Writes or fixes the code the task requires.',
      },
      debugger: {
        name: 'Debugger',
        description: 'Finds the root cause of bugs and proposes verified fixes.',
      },
      tester: {
        name: 'Test Expert',
        description: 'Produces test scenarios and edge cases.',
      },
      reviewer: {
        name: 'Code Reviewer',
        description: 'Reviews code for quality, security, and style.',
      },
      documenter: {
        name: 'Documentation Expert',
        description: 'Writes usage documentation and examples for the delivered code.',
      },
    },
  },
  finance: {
    name: 'Finance Expert',
    description:
      'Expert in financial analysis, budgeting, investment research, and market data interpretation.',
    capabilities: [
      'Financial analysis',
      'Budgeting',
      'Investment research',
      'Market data',
    ],
    team: {
      market_data: {
        name: 'Market Data Analyst',
        description: 'Collects price, volume, and fundamental market data.',
      },
      prediction_markets: {
        name: 'Prediction Markets Analyst',
        description:
          'Analyzes odds and signals from prediction markets such as Polymarket.',
      },
      news: {
        name: 'News Aggregator',
        description: 'Compiles current financial news relevant to the topic.',
      },
      sentiment: {
        name: 'Sentiment Analyst',
        description: 'Measures market and social media sentiment.',
      },
      risk: {
        name: 'Macro & Risk Analyst',
        description: 'Assesses the macro context and grades downside risks.',
      },
      analyst: {
        name: 'Financial Analyst & Reporter',
        description: 'Turns findings into financial analysis and a clear report.',
      },
    },
  },
  marketing: {
    name: 'Marketing Expert',
    description:
      'Expert in campaign planning, brand strategy, copywriting, and growth tactics.',
    capabilities: [
      'Campaign planning',
      'Brand strategy',
      'Copywriting',
      'Growth tactics',
    ],
    team: {
      audience: {
        name: 'Audience Analyst',
        description: 'Analyzes the target audience, its needs, and segments.',
      },
      competitor: {
        name: 'Competitive Analyst',
        description: 'Maps how rivals position themselves and where the open claim is.',
      },
      strategist: {
        name: 'Strategy Expert',
        description: 'Designs the campaign and brand strategy.',
      },
      copywriter: {
        name: 'Copywriter',
        description: 'Writes persuasive marketing copy and slogans.',
      },
      growth: {
        name: 'Channel & Growth Expert',
        description: 'Recommends channel selection, budget, and growth tactics.',
      },
    },
  },
  seo: {
    name: 'SEO Expert',
    description:
      'Expert in keyword research, site auditing, content optimization, and search ranking improvement.',
    capabilities: [
      'Keyword research',
      'Site auditing',
      'Content optimization',
      'Backlink analysis',
    ],
    team: {
      keywords: {
        name: 'Keyword Analyst',
        description: 'Extracts keyword opportunities and search intent.',
      },
      content_audit: {
        name: 'Content Auditor',
        description: 'Audits and improves content for on-page SEO.',
      },
      technical: {
        name: 'Technical SEO Expert',
        description: 'Examines site speed, indexing, and technical SEO issues.',
      },
      backlinks: {
        name: 'Backlink & Authority Analyst',
        description: 'Builds the backlink profile and domain authority strategy.',
      },
      strategist: {
        name: 'SEO Strategist',
        description:
          "Merges the specialists' findings into one prioritized, sequenced action plan.",
      },
    },
  },
  searching: {
    name: 'Search Expert',
    description:
      'Expert in quickly finding and verifying specific information, sources, and facts on the web.',
    capabilities: [
      'Web search',
      'Source finding',
      'Fact verification',
      'Quick summarization',
    ],
    team: {
      query_planner: {
        name: 'Query Planner',
        description: 'Breaks the search into the most efficient queries and plans them.',
      },
      web_searcher: {
        name: 'Web Searcher',
        description: 'Performs targeted searches across general web sources.',
      },
      news_searcher: {
        name: 'News Searcher',
        description: 'Scans current news sources.',
      },
      deep_searcher: {
        name: 'Deep Source Searcher',
        description: 'Searches deeply across academic, official, and primary sources.',
      },
      verifier: {
        name: 'Verifier',
        description: 'Cross-checks and verifies the information found.',
      },
      summarizer: {
        name: 'Summarizer',
        description: 'Distills verified findings into a clear, sourced summary.',
      },
    },
  },
  research: {
    name: 'Research Expert',
    description:
      'Expert in multi-source in-depth analysis, synthesis, and comprehensive report writing.',
    capabilities: [
      'Deep analysis',
      'Multi-source synthesis',
      'Report writing',
      'Literature review',
    ],
    team: {
      collector: {
        name: 'Source Collector',
        description: 'Gathers diverse and reliable sources relevant to the topic.',
      },
      analyst: {
        name: 'Analyst',
        description: 'Analyzes the collected material in depth.',
      },
      critic: {
        name: 'Critic',
        description: 'Surfaces opposing views and weak points.',
      },
      synthesizer: {
        name: 'Synthesizer',
        description: 'Turns the analysis and critique into a coherent whole.',
      },
      writer: {
        name: 'Report Writer',
        description: 'Turns the conclusions into a structured report.',
      },
    },
  },
  data: {
    name: 'Data Expert',
    description:
      'Expert in data analysis, statistics, visualization, and data pipeline design.',
    capabilities: [
      'Data analysis',
      'Statistics',
      'Visualization',
      'Data pipelines',
    ],
    team: {
      collector: {
        name: 'Data Collector',
        description: 'Finds the required data; documents source, schema, and license.',
      },
      cleaner: {
        name: 'Data Cleaner',
        description: 'Cleans the data, fixing gaps and inconsistencies.',
      },
      statistician: {
        name: 'Statistician',
        description: 'Performs statistical analysis and modeling.',
      },
      visualizer: {
        name: 'Visualizer',
        description: 'Designs appropriate visualizations for the findings.',
      },
      critic: {
        name: 'Statistical Critic',
        description:
          'Attacks the analysis: sample validity, confounders, and overstated causality.',
      },
      interpreter: {
        name: 'Interpreter & Reporter',
        description: 'Translates results into business language and reports them.',
      },
    },
  },
  content: {
    name: 'Content & Writing Expert',
    description:
      'Expert in writing and editing blog posts, articles, scripts, stories, and social media content.',
    capabilities: [
      'Blog & article writing',
      'Script & story writing',
      'Social media content',
      'Editing & style',
    ],
    team: {
      planner: {
        name: 'Content Planner',
        description: 'Defines the audience, angle, and section-level outline.',
      },
      researcher: {
        name: 'Content Researcher',
        description: 'Sources the facts, figures, and examples the draft cites.',
      },
      stylist: {
        name: 'Style & Voice Expert',
        description: 'Defines the voice/tone guide suited to the platform and audience.',
      },
      writer: {
        name: 'Content Writer',
        description: 'Writes the full text faithful to the outline and voice guide.',
      },
      headline: {
        name: 'Headline & Hook Expert',
        description: 'Produces headline, hook, opening line, and CTA variants.',
      },
      critic: {
        name: 'Content Critic',
        description: 'Reads the text critically; finds weak points and clichés.',
      },
      editor: {
        name: 'Editor',
        description: 'Applies the critique and produces the publication-ready final text.',
      },
    },
  },
  legal: {
    name: 'Legal & Compliance Expert',
    description:
      'Expert in contract review, KVKK/GDPR compliance, license analysis, and legal risk detection.',
    capabilities: [
      'Contract review',
      'KVKK/GDPR compliance',
      'License analysis',
      'Risk detection',
    ],
    team: {
      researcher: {
        name: 'Legal Researcher',
        description: 'Finds the relevant legislation and official guidance with effective dates.',
      },
      contracts: {
        name: 'Contract Analyst',
        description: 'Reviews the contract clause by clause; extracts obligations and risks.',
      },
      privacy: {
        name: 'KVKK & GDPR Expert',
        description: 'Compares data processing against KVKK and GDPR requirements.',
      },
      licenses: {
        name: 'License Analyst',
        description: 'Analyzes software/content licenses and compliance conflicts.',
      },
      risk: {
        name: 'Risk Assessor',
        description: 'Turns findings into a severity-ranked risk register.',
      },
      reporter: {
        name: 'Compliance Reporter',
        description: 'Reports findings in plain language; ends with a legal disclaimer.',
      },
    },
  },
  education: {
    name: 'Education & Learning Expert',
    description:
      'Expert in curriculum design, lesson planning, quiz generation, and concept explanation.',
    capabilities: [
      'Curriculum design',
      'Lesson planning',
      'Quiz generation',
      'Concept explanation',
    ],
    team: {
      curriculum: {
        name: 'Curriculum Designer',
        description: 'Defines measurable objectives, module order, and scope.',
      },
      lesson_planner: {
        name: 'Lesson Planner',
        description: 'Turns modules into lesson plans with activities, timing, and materials.',
      },
      explainer: {
        name: 'Concept Explainer',
        description: 'Explains concepts with analogies and worked examples.',
      },
      quiz_maker: {
        name: 'Assessment Designer',
        description: 'Prepares quizzes and answer keys aligned with the objectives.',
      },
      pedagogue: {
        name: 'Pedagogy Auditor',
        description: 'Audits objective-content-assessment alignment and level fit.',
      },
    },
  },
  social: {
    name: 'Social Listening Analyst',
    description:
      'Measures what people are actually saying about a brand, product, or topic: volume, sentiment drivers, themes, and who drives the conversation.',
    capabilities: [
      'Social listening',
      'Sentiment and emotion analysis',
      'Theme and narrative tracking',
      'Influencer and amplification mapping',
    ],
    team: {
      pulse: {
        name: 'Volume & Engagement Analyst',
        description: 'Measures how much is being said and how far it travels.',
      },
      sentiment: {
        name: 'Sentiment Analyst',
        description:
          'Classifies sentiment and names what is actually driving it.',
      },
      narrative: {
        name: 'Theme & Narrative Analyst',
        description:
          'Clusters the conversation into themes and tracks how they move.',
      },
      voices: {
        name: 'Voices & Amplification Analyst',
        description:
          'Identifies who carries the conversation and whether it is organic.',
      },
      brief: {
        name: 'Listening Brief Writer',
        description:
          'Synthesizes a decision-ready read with explicit confidence.',
      },
    },
  },
  community: {
    name: 'Community Signal Analyst',
    description:
      "Turns your own community's chatter into a ranked, evidence-backed product backlog: recurring pain points, requests, and what changed.",
    capabilities: [
      'Community feedback mining',
      'Issue clustering and prioritisation',
      'Trend and spike detection',
      'Backlog generation from evidence',
    ],
    team: {
      themes: {
        name: 'Feedback Clusterer',
        description:
          'Groups community messages into recurring pain points and requests.',
      },
      sentiment: {
        name: 'Sentiment Analyst',
        description:
          'Reads the tone behind each cluster and flags churn-risk language.',
      },
      severity: {
        name: 'Prioritisation Analyst',
        description: 'Scores each cluster by frequency, severity, and recency.',
      },
      trends: {
        name: 'Trend Analyst',
        description:
          'Separates new spikes from chronic, long-running complaints.',
      },
      product: {
        name: 'Product Signal Writer',
        description: 'Turns the top clusters into assignable backlog items.',
      },
    },
  },
  opensource: {
    name: 'Open Source Analyst',
    description:
      'Evaluates third-party open-source projects and dependencies: maintenance health, community risk, licensing, and adoption verdicts.',
    capabilities: [
      'Dependency due diligence',
      'Repository health metrics',
      'Maintenance and license risk',
      'Adopt / avoid verdicts',
    ],
    team: {
      profiler: {
        name: 'Project Profiler',
        description:
          'Establishes what the project is, its license, and how it ships.',
      },
      health: {
        name: 'Health Analyst',
        description:
          'Measures commit cadence, bus factor, and issue close times.',
      },
      maintainers: {
        name: 'Maintainer & Community Analyst',
        description:
          'Judges maintainer responsiveness, backlog shape, and succession risk.',
      },
      risk: {
        name: 'Risk Assessor',
        description:
          'Names maintenance, security, and licensing risks with mitigations.',
      },
      alternatives: {
        name: 'Alternatives Researcher',
        description:
          'Finds and measures what a team would use instead, and what switching would cost.',
      },
      verdict: {
        name: 'Adoption Verdict',
        description:
          'Calls adopt, watch, or avoid, and names the decisive metric.',
      },
    },
  },
  local: {
    name: 'Local Market Analyst',
    description:
      'Maps the competitors in a physical area and mines their reviews to find rating distributions, recurring complaints, and market gaps.',
    capabilities: [
      'Local competitor mapping',
      'Rating and review distribution',
      'Review theme mining',
      'Market gap analysis',
    ],
    team: {
      mapper: {
        name: 'Market Mapper',
        description: 'Finds the real competitor set in a specific area.',
      },
      metrics: {
        name: 'Market Metrics Analyst',
        description:
          'Computes the rating, review-volume, and price distribution.',
      },
      reviews: {
        name: 'Review Miner',
        description:
          'Extracts recurring praise and complaint themes from reviews.',
      },
      gap: {
        name: 'Gap Analyst',
        description: 'Ranks unmet demand and recommends a positioning.',
      },
    },
  },
  general: {
    name: 'General Expert',
    description:
      'Versatile general expert for any task that does not fit a specific domain.',
    capabilities: ['General tasks', 'Writing', 'Planning', 'Summarization'],
    team: {
      researcher: {
        name: 'Researcher',
        description: 'Gathers the information the task requires.',
      },
      writer: {
        name: 'Writer',
        description: 'Produces the main output (text, plan, summary, etc.).',
      },
      checker: {
        name: 'Checker',
        description: 'Checks the output for accuracy and completeness.',
      },
    },
  },
  // --- build ---------------------------------------------------------
  devops: {
    name: 'DevOps & Reliability Engineer',
    description:
      'Maps how a system is built, released and observed, then writes the ' +
      'ordered operational procedure for running and recovering it.',
    capabilities: [
      'Deployment topology mapping',
      'CI/CD and release engineering',
      'Observability and SLO design',
      'Incident response and runbooks',
    ],
    team: {
      topology: {
        name: 'Topology Mapper',
        description: 'Maps the system, its stack, and where each part runs.',
      },
      pipeline: {
        name: 'Pipeline Engineer',
        description: 'Maps CI/CD, build and release mechanics as they exist.',
      },
      observability: {
        name: 'Observability Engineer',
        description: 'Defines metrics, logs, traces, alerts and SLOs.',
      },
      incident: {
        name: 'Failure Mode Analyst',
        description: 'Enumerates failure modes, blast radius and rollback.',
      },
      runbook: {
        name: 'Runbook Author',
        description: 'Writes the concrete, ordered operational procedure.',
      },
    },
  },
  security: {
    name: 'Security & AppSec Analyst',
    description:
      'Maps a system\'s attack surface, traces exploit paths through the code ' +
      'and its dependencies, and ranks findings by exploitability and impact.',
    capabilities: [
      'Attack surface mapping',
      'Dependency and supply-chain review',
      'Secure code analysis',
      'CVE and advisory exposure',
    ],
    team: {
      surface: {
        name: 'Attack Surface Analyst',
        description: 'Maps entry points, trust boundaries and exposure.',
      },
      dependencies: {
        name: 'Supply-Chain Analyst',
        description: 'Reviews dependencies and their upstream repositories.',
      },
      code_review: {
        name: 'Secure Code Analyst',
        description: 'Traces untrusted input into sinks in the code itself.',
      },
      exposure: {
        name: 'Vulnerability Intelligence Analyst',
        description: 'Finds published CVEs affecting the components in use.',
      },
      report: {
        name: 'Security Report Author',
        description: 'Ranks the findings and writes the remediation order.',
      },
    },
  },
  qa: {
    name: 'QA & Test Strategist',
    description:
      'Ranks what can break and what it costs, designs the cases and fixtures ' +
      'that catch it, builds the runnable harness, and writes the ordered ' +
      'test plan with exit criteria.',
    capabilities: [
      'Risk-based test strategy',
      'Edge and negative case design',
      'Test automation and harnesses',
      'Fixtures and test data',
    ],
    team: {
      risk_map: {
        name: 'Risk Analyst',
        description: 'Ranks what can break and what each failure costs.',
      },
      cases: {
        name: 'Test Case Designer',
        description: 'Designs the case matrix, including edge and negatives.',
      },
      automation: {
        name: 'Automation Engineer',
        description: 'Writes and runs the executable test harness.',
      },
      data_sets: {
        name: 'Test Data Engineer',
        description: 'Builds the fixtures, including the hostile data.',
      },
      plan: {
        name: 'Test Plan Author',
        description: 'Writes the ordered plan with coverage and exit criteria.',
      },
    },
  },
  cloud: {
    name: 'Cloud Architecture Advisor',
    description:
      'Turns load, latency and compliance constraints into a sized cloud ' +
      'topology with a cost model, a failure-domain map, and one recommended ' +
      'architecture with its trade-offs stated.',
    capabilities: [
      'Requirements quantification',
      'Compute and storage topology',
      'Cloud cost modelling',
      'Failure domains and recovery',
    ],
    team: {
      requirements: {
        name: 'Requirements Analyst',
        description:
          'States load, latency, durability and compliance as numbers.',
      },
      topology: {
        name: 'Topology Designer',
        description: 'Shapes the compute, storage, network and data flow.',
      },
      cost: {
        name: 'Cost Analyst',
        description: 'Builds the cost model and ranks its drivers.',
      },
      resilience: {
        name: 'Resilience Engineer',
        description: 'Maps failure domains, degradation and recovery.',
      },
      design: {
        name: 'Architecture Author',
        description: 'Recommends the architecture and its trade-offs.',
      },
    },
  },
  apidesign: {
    name: 'API & Integration Designer',
    description:
      'Designs the contract an API exposes: resource model, endpoints and ' +
      'status codes, error shape, pagination, versioning, auth and rate ' +
      'limits, delivered as a specification with worked examples.',
    capabilities: [
      'Resource and domain modelling',
      'Endpoint and error contract design',
      'Versioning and deprecation policy',
      'API auth, scopes and rate limits',
    ],
    team: {
      resources: {
        name: 'Domain Modeller',
        description: 'Models the resources the API exposes.',
      },
      contract: {
        name: 'Contract Designer',
        description: 'Defines endpoints, statuses, errors and pagination.',
      },
      versioning: {
        name: 'Compatibility Strategist',
        description: 'Sets the versioning and deprecation strategy.',
      },
      auth: {
        name: 'Access Designer',
        description: 'Designs authentication, scopes and rate limits.',
      },
      spec: {
        name: 'Specification Author',
        description: 'Writes the OpenAPI-shaped contract with examples.',
      },
    },
  },
  mobile: {
    name: 'Mobile App Engineer',
    description:
      'Builds iOS, Android and cross-platform apps: platform constraints, app ' +
      'architecture and offline behaviour, implementation, on-device ' +
      'performance, and the store release path.',
    capabilities: [
      'Platform and framework selection',
      'App architecture and offline design',
      'Native and cross-platform implementation',
      'Device performance and store release',
    ],
    team: {
      platform: {
        name: 'Platform Analyst',
        description: 'Fixes the platform, minimum OS and capability needs.',
      },
      architect: {
        name: 'App Architect',
        description: 'Designs navigation, state, data and offline behaviour.',
      },
      coder: {
        name: 'Mobile Engineer',
        description: 'Implements the feature in the platform\'s idiom.',
      },
      performance: {
        name: 'Performance Engineer',
        description: 'Tunes startup, frame time, memory, battery and size.',
      },
      release: {
        name: 'Release Manager',
        description: 'Plans signing, store review and the staged rollout.',
      },
    },
  },
  gamedev: {
    name: 'Game Development Expert',
    description:
      'Designs the core loop, chooses the engine and architecture, writes the ' +
      'gameplay code, prices it against the frame budget, and plans the ' +
      'asset, audio and level pipeline.',
    capabilities: [
      'Core loop and mechanics design',
      'Engine and systems architecture',
      'Gameplay programming',
      'Frame budget and asset pipeline',
    ],
    team: {
      design: {
        name: 'Game Designer',
        description:
          'Defines the mechanics, the loop and the player experience.',
      },
      systems: {
        name: 'Systems Architect',
        description: 'Chooses the engine and the systems architecture.',
      },
      implementer: {
        name: 'Gameplay Programmer',
        description: 'Writes the gameplay code with its tunables exposed.',
      },
      performance: {
        name: 'Performance Engineer',
        description: 'Prices the work against the frame budget.',
      },
      production: {
        name: 'Production Lead',
        description: 'Plans the asset, audio and level pipeline.',
      },
    },
  },
  // --- market --------------------------------------------------------
  product: {
    name: 'Product Management Expert',
    description:
      'Turns a request into an evidenced problem, a scoped slice with an ' +
      'explicit cut list, and a requirements document with its metric.',
    capabilities: [
      'Problem definition and evidence',
      'Competitive and market context',
      'Scoping and prioritization',
      'Success metrics and PRDs',
    ],
    team: {
      problem: {
        name: 'Problem Analyst',
        description: 'States the user problem and the evidence it is real.',
      },
      research: {
        name: 'Product Researcher',
        description:
          'Finds how comparable products solve this specific problem.',
      },
      scope: {
        name: 'Scoping Lead',
        description: 'Defines the shippable slice and the explicit cut list.',
      },
      metrics: {
        name: 'Metrics Designer',
        description: 'Defines the success metric and its counter-metric.',
      },
      prd: {
        name: 'Requirements Author',
        description:
          'Writes the requirements document the reader actually receives.',
      },
    },
  },
  sales: {
    name: 'Sales & Revenue Expert',
    description:
      'Builds a runnable sales motion: an ICP of observable signals, trigger- ' +
      'based account research, answered objections, and outreach.',
    capabilities: [
      'ICP and qualification',
      'Account and trigger research',
      'Objection handling',
      'Outreach sequences and playbooks',
    ],
    team: {
      icp: {
        name: 'ICP Analyst',
        description:
          'Defines the ideal customer by observable qualifying signals.',
      },
      prospect: {
        name: 'Account Researcher',
        description: 'Researches target accounts and their trigger events.',
      },
      objections: {
        name: 'Objection Analyst',
        description: 'Collects the real objections and the evidence for each.',
      },
      outreach: {
        name: 'Outreach Writer',
        description: 'Writes the message sequence and picks each channel.',
      },
      playbook: {
        name: 'Playbook Author',
        description: 'Assembles the runnable motion the reader receives.',
      },
    },
  },
  ads: {
    name: 'Paid Ads & Performance Marketer',
    description:
      'Plans paid acquisition: buyable targeting, a priced channel mix, ' +
      'distinct ad angles, and break-even math with kill criteria.',
    capabilities: [
      'Paid targeting and audiences',
      'Channel mix and media costs',
      'Ad creative angles',
      'CAC, break-even and test design',
    ],
    team: {
      audience: {
        name: 'Audience Strategist',
        description:
          'Turns the buyer into signals a platform can actually buy.',
      },
      channels: {
        name: 'Channel Strategist',
        description: 'Prices the channel mix and says what each is good at.',
      },
      creative: {
        name: 'Creative Strategist',
        description: 'Writes the ad angles and the copy for each.',
      },
      budget: {
        name: 'Unit Economics Analyst',
        description:
          'Computes allowable CAC, media assumptions and break-even.',
      },
      plan: {
        name: 'Launch Planner',
        description: 'Assembles the launch plan the reader receives.',
      },
    },
  },
  brand: {
    name: 'Brand & PR Strategist',
    description:
      'Finds the position a brand can credibly own, evidences how it is ' +
      'perceived today, and writes the narrative, press angle and brief.',
    capabilities: [
      'Brand positioning',
      'Perception and reputation analysis',
      'Narrative and message hierarchy',
      'Press angles and messaging briefs',
    ],
    team: {
      positioning: {
        name: 'Positioning Strategist',
        description: 'Finds the credible position and names who it takes from.',
      },
      perception: {
        name: 'Perception Analyst',
        description: 'Evidences how the brand is actually described today.',
      },
      narrative: {
        name: 'Narrative Strategist',
        description: 'Builds the story and the message hierarchy under it.',
      },
      press: {
        name: 'Press Strategist',
        description:
          'Finds the angle a journalist would run, and who to pitch.',
      },
      brief: {
        name: 'Messaging Brief Author',
        description: 'Writes the messaging brief the reader receives.',
      },
    },
  },
  ecommerce: {
    name: 'E-commerce Operations Expert',
    description:
      'Diagnoses an online store end to end — listings, funnel leaks, ' +
      'shipping and returns, repeat purchase — and ranks the fixes.',
    capabilities: [
      'Catalogue and merchandising',
      'Conversion funnel diagnosis',
      'Fulfilment, shipping and returns',
      'Retention, LTV and margin',
    ],
    team: {
      catalog: {
        name: 'Catalogue Analyst',
        description: 'Reviews listings, merchandising and price structure.',
      },
      funnel: {
        name: 'Funnel Analyst',
        description: 'Maps the conversion funnel and locates the leak.',
      },
      logistics: {
        name: 'Fulfilment & Returns Analyst',
        description: 'Assesses shipping and returns as cost and experience.',
      },
      retention: {
        name: 'Retention & LTV Analyst',
        description: 'Computes repeat rate, LTV and contribution margin.',
      },
      actions: {
        name: 'Action Planner',
        description: 'Produces the single ranked list of changes to make.',
      },
    },
  },
  // --- money ---------------------------------------------------------
  crypto: {
    name: 'Crypto & Digital Asset Analyst',
    description:
      'Assesses tokens, protocols and chains from mechanism and public on- ' +
      'chain data: supply and emissions, holder concentration, activity, ' +
      'narrative, and custody, contract and regulatory risk.',
    capabilities: [
      'Protocol and token mechanism analysis',
      'Tokenomics, supply and unlock schedules',
      'On-chain activity and holder concentration',
      'Custody, contract and regulatory risk',
    ],
    team: {
      asset: {
        name: 'Asset & Protocol Researcher',
        description: 'Establishes what the asset is and what it claims to do.',
      },
      onchain: {
        name: 'On-Chain & Tokenomics Analyst',
        description: 'Reports supply, emissions, concentration and activity.',
      },
      sentiment: {
        name: 'Narrative Analyst',
        description:
          'Maps the story attached to the asset and who is pushing it.',
      },
      risk: {
        name: 'Digital Asset Risk Analyst',
        description:
          'Rates custody, contract, counterparty and regulatory risk.',
      },
      verdict: {
        name: 'Assessment Writer',
        description: 'Writes the final assessment and what would falsify it.',
      },
    },
  },
  econ: {
    name: 'Economics & Public Data Analyst',
    description:
      'Answers questions from official economic and public statistics: ' +
      'choosing the right series, retrieving the real figures with their ' +
      'vintage, computing the transforms, and interpreting what they support.',
    capabilities: [
      'Economic indicator selection',
      'Official statistics retrieval',
      'Real, seasonal and index transforms',
      'Policy and historical interpretation',
    ],
    team: {
      indicators: {
        name: 'Indicator Specialist',
        description: 'Chooses the series that answer the question.',
      },
      series: {
        name: 'Statistical Data Retriever',
        description: 'Pulls the real figures with vintage and units.',
      },
      compute: {
        name: 'Quantitative Analyst',
        description: 'Runs the transforms and shows the arithmetic.',
      },
      context: {
        name: 'Policy & History Analyst',
        description:
          'Supplies the context that makes the number mean something.',
      },
      interpreter: {
        name: 'Interpretation Writer',
        description:
          'States what the data supports, what it does not, and how sure.',
      },
    },
  },
  personalfinance: {
    name: 'Personal Finance Planner',
    description:
      'Turns a household\'s stated position into an ordered plan: cash flow ' +
      'and runway, the vehicles available in their jurisdiction, projected ' +
      'scenarios, and what to do first.',
    capabilities: [
      'Cash flow and runway analysis',
      'Debt payoff and saving strategy',
      'Jurisdiction-specific saving vehicles',
      'Compounding and amortisation projections',
    ],
    team: {
      situation: {
        name: 'Position Analyst',
        description:
          'States the household position in numbers and names the gaps.',
      },
      options: {
        name: 'Options Analyst',
        description:
          'Lists the vehicles available in the user\'s jurisdiction.',
      },
      projection: {
        name: 'Projection Analyst',
        description: 'Computes the compounding, amortisation and scenarios.',
      },
      plan: {
        name: 'Plan Writer',
        description: 'Writes the ordered plan with costs and triggers.',
      },
    },
  },
  tax: {
    name: 'Tax & Accounting Advisor',
    description:
      'Works out how income and transactions are taxed: which jurisdiction ' +
      'and tax year apply, how each item is characterised, the rates and ' +
      'arithmetic, and the forms, deadlines and records required.',
    capabilities: [
      'Jurisdiction and residency determination',
      'Income and transaction characterisation',
      'Rate, bracket and liability calculation',
      'Filing deadlines and record retention',
    ],
    team: {
      jurisdiction: {
        name: 'Jurisdiction & Residency Analyst',
        description: 'Establishes whose rules apply and for which tax year.',
      },
      classification: {
        name: 'Characterisation Analyst',
        description: 'Characterises each item, since the treatment follows it.',
      },
      calculation: {
        name: 'Tax Computation Analyst',
        description: 'Applies the rates, brackets and thresholds.',
      },
      filings: {
        name: 'Compliance & Filings Analyst',
        description: 'Lists the forms, deadlines and retention requirements.',
      },
      summary: {
        name: 'Position Summary Writer',
        description:
          'States the position, the amounts and where sign-off is needed.',
      },
    },
  },
  // --- operate -------------------------------------------------------
  hr: {
    name: 'HR & Talent Expert',
    description:
      'Turns a hiring need into a usable package: a levelled role, a sourcing ' +
      'plan, an interview loop with rubrics, and a benchmarked offer.',
    capabilities: [
      'Role definition and levelling',
      'Sourcing strategy',
      'Interview loop and rubric design',
      'Compensation benchmarking',
    ],
    team: {
      role: {
        name: 'Role Definition Specialist',
        description:
          'Defines what the role owns and levels it by accountability.',
      },
      sourcing: {
        name: 'Sourcing Strategist',
        description: 'Finds where these candidates are and what reaches them.',
      },
      assessment: {
        name: 'Interview Loop Designer',
        description: 'Designs the loop: what each stage tests and its rubric.',
      },
      compensation: {
        name: 'Compensation Analyst',
        description: 'Benchmarks the range with sources and a geography.',
      },
      package: {
        name: 'Hiring Package Writer',
        description: 'Assembles the postable description, loop, and offer.',
      },
    },
  },
  project: {
    name: 'Project & Delivery Manager',
    description:
      'Turns a piece of work into a defensible plan: bounded scope, estimates ' +
      'with uncertainty, a critical path with owners, and dated milestones.',
    capabilities: [
      'Scope definition and boundary setting',
      'Work breakdown and estimation',
      'Critical path and dependency mapping',
      'Risk register and delivery planning',
    ],
    team: {
      scope: {
        name: 'Scope Definition Specialist',
        description:
          'Defines the deliverables and what is explicitly out of scope.',
      },
      breakdown: {
        name: 'Estimation Analyst',
        description:
          'Breaks the scope into tasks with estimates and uncertainty.',
      },
      dependencies: {
        name: 'Dependency Analyst',
        description: 'Maps the critical path, the blockers, and their owners.',
      },
      risks: {
        name: 'Delivery Risk Analyst',
        description: 'Builds the risk register with mitigations and triggers.',
      },
      plan: {
        name: 'Delivery Planner',
        description: 'Sequences the work into dated, demonstrable milestones.',
      },
    },
  },
  procurement: {
    name: 'Procurement & Vendor Analyst',
    description:
      'Picks a vendor defensibly: testable requirements, a candidate set with ' +
      'the option you missed, total cost of ownership, and exit cost.',
    capabilities: [
      'Testable requirement definition',
      'Vendor landscape and candidate discovery',
      'Scored comparison and total cost of ownership',
      'Lock-in, exit cost and negotiation preparation',
    ],
    team: {
      requirements: {
        name: 'Requirements Analyst',
        description:
          'States the must-haves as things a vendor can be tested on.',
      },
      vendors: {
        name: 'Vendor Landscape Analyst',
        description:
          'Assembles the candidate set, including the option you missed.',
      },
      evaluation: {
        name: 'Evaluation Analyst',
        description: 'Scores the candidates on cost of ownership and lock-in.',
      },
      recommendation: {
        name: 'Procurement Advisor',
        description: 'Names the pick, the runner-up, and what would flip it.',
      },
    },
  },
  support: {
    name: 'Customer Support Operations',
    description:
      'Runs the support queue: what users are reporting right now, how it ' +
      'triages, what to reply today, and what to fix this week.',
    capabilities: [
      'Support intake and issue grouping',
      'Severity triage by user impact',
      'Bug versus documentation versus expectation diagnosis',
      'Reply and macro drafting',
    ],
    team: {
      intake: {
        name: 'Support Intake Analyst',
        description: 'Collects what users are actually reporting, verbatim.',
      },
      triage: {
        name: 'Triage Lead',
        description: 'Groups reports and scores severity by who is blocked.',
      },
      root_cause: {
        name: 'Root Cause Analyst',
        description: 'Separates a bug from a docs gap from an expectation gap.',
      },
      responses: {
        name: 'Response Writer',
        description: 'Writes the sendable reply and macro for each group.',
      },
      actions: {
        name: 'Support Operations Lead',
        description: 'Ranks the fix-and-communicate list with owners.',
      },
    },
  },
  // --- life ----------------------------------------------------------
  travel: {
    name: 'Travel & Itinerary Planner',
    description:
      'Plans trips end to end: what is worth seeing, how to move between it, ' +
      'where to stay, what it costs, and a day-by-day itinerary that respects ' +
      'real travel times.',
    capabilities: [
      'Destination scouting',
      'Transport and entry logistics',
      'Neighbourhood selection',
      'Trip budgeting',
      'Day-by-day itinerary building',
    ],
    team: {
      destination: {
        name: 'Destination Scout',
        description: 'Finds what is actually there and worth the time.',
      },
      logistics: {
        name: 'Logistics Planner',
        description: 'Works out getting there, moving around, and entry rules.',
      },
      stays: {
        name: 'Accommodation Advisor',
        description:
          'Chooses the area to stay in and says what it trades away.',
      },
      budget: {
        name: 'Budget Estimator',
        description: 'Builds a costed estimate with its assumptions stated.',
      },
      itinerary: {
        name: 'Itinerary Writer',
        description: 'Writes the day-by-day plan the traveller carries.',
      },
    },
  },
  career: {
    name: 'Career & Resume Coach',
    description:
      'Turns a person\'s history into outcome-based CV material, measures it ' +
      'against what target roles currently ask for, and produces the ' +
      'narrative and the ordered next actions to close the distance.',
    capabilities: [
      'Outcome-based CV rewriting',
      'Target role and posting analysis',
      'Honest gap assessment',
      'Career narrative building',
      'Ordered action planning',
    ],
    team: {
      profile: {
        name: 'Profile Analyst',
        description: 'Restates what the person did as outcomes with numbers.',
      },
      market: {
        name: 'Market Analyst',
        description: 'Finds what the target roles currently ask for.',
      },
      gaps: {
        name: 'Gap Analyst',
        description: 'Measures the honest distance to the target.',
      },
      narrative: {
        name: 'Narrative Strategist',
        description: 'Builds the through-line and answers the objection.',
      },
      package: {
        name: 'Package Writer',
        description: 'Writes the CV bullets, summary and next actions.',
      },
    },
  },
  health: {
    name: 'Health Information Analyst',
    description:
      'Synthesises published health evidence and official guidance into a ' +
      'plain-language answer with its confidence, its interactions and its ' +
      'red flags. Information synthesis, not diagnosis or treatment advice.',
    capabilities: [
      'Clinical question framing',
      'Evidence weighting by study type and size',
      'Guideline review with body and year',
      'Interaction and contraindication analysis',
      'Plain-language health explanation',
    ],
    team: {
      question: {
        name: 'Question Framer',
        description:
          'States the question clinically and names what is unknown.',
      },
      evidence: {
        name: 'Evidence Analyst',
        description: 'Weighs the published evidence by study type and size.',
      },
      guidelines: {
        name: 'Guideline Analyst',
        description: 'Reports what official bodies currently recommend.',
      },
      caveats: {
        name: 'Safety Analyst',
        description: 'Names interactions, contraindications and red flags.',
      },
      summary: {
        name: 'Plain-Language Writer',
        description: 'Writes the answer with its confidence and its limits.',
      },
    },
  },
  food: {
    name: 'Food & Nutrition Expert',
    description:
      'Turns dietary constraints into a cookable week: allergy-cleared ' +
      'recipes chosen for ingredient reuse, portioned properly, with a ' +
      'shopping list, a prep order, and a substitute for everything.',
    capabilities: [
      'Dietary constraint and allergen analysis',
      'Macro and micronutrient planning',
      'Recipe development with ingredient reuse',
      'Weekly meal planning and shopping lists',
    ],
    team: {
      requirements: {
        name: 'Requirements Analyst',
        description: 'Establishes allergies first, then the other constraints.',
      },
      nutrition: {
        name: 'Nutrition Analyst',
        description: 'Sets macros, at-risk micronutrients and portions.',
      },
      recipes: {
        name: 'Recipe Developer',
        description:
          'Builds dishes that clear the constraints and reuse stock.',
      },
      plan: {
        name: 'Meal Plan Writer',
        description: 'Writes the plan, shopping list, prep order and swaps.',
      },
    },
  },
  // --- knowledge -----------------------------------------------------
  scholar: {
    name: 'Academic Literature Analyst',
    description:
      'Searches, appraises and synthesizes academic literature: what the ' +
      'studies actually found, how good they are, and where the field agrees, ' +
      'disputes, or has never looked.',
    capabilities: [
      'Systematic literature search',
      'Methodology appraisal',
      'Consensus and gap mapping',
      'Evidence-graded synthesis',
    ],
    team: {
      question: {
        name: 'Research Question Specialist',
        description:
          'Turns the request into a question the literature can answer.',
      },
      search: {
        name: 'Literature Search Specialist',
        description: 'Runs and records the literature search itself.',
      },
      appraisal: {
        name: 'Methodology Appraiser',
        description:
          'Rates each study on design, sample, controls and conflicts.',
      },
      consensus: {
        name: 'Consensus & Gap Analyst',
        description: 'Maps agreement, genuine dispute, and unstudied gaps.',
      },
      synthesis: {
        name: 'Evidence Synthesis Lead',
        description: 'Writes the graded synthesis the reader acts on.',
      },
    },
  },
  journalism: {
    name: 'Journalism & Fact-check',
    description:
      'Isolates the checkable claims in a story, chases the primary sources, ' +
      'traces where the claim came from, and issues a verdict per claim with ' +
      'the evidence behind it.',
    capabilities: [
      'Claim isolation',
      'Primary source verification',
      'Provenance and circulation tracing',
      'Fact-check write-up',
    ],
    team: {
      claim: {
        name: 'Claim Isolator',
        description: 'Separates the checkable propositions from the rhetoric.',
      },
      primary: {
        name: 'Primary Source Researcher',
        description: 'Chases the document, filing or dataset itself.',
      },
      chatter: {
        name: 'Circulation & Provenance Analyst',
        description: 'Traces what is circulating and where it started.',
      },
      verification: {
        name: 'Verification Analyst',
        description: 'Issues a verdict per claim with evidence and confidence.',
      },
      story: {
        name: 'Fact-check Writer',
        description: 'Writes the published fact-check the reader acts on.',
      },
    },
  },
  translation: {
    name: 'Translation & Localization Expert',
    description:
      'Translates and localizes text with a glossary, the right register, and ' +
      'adapted idiom, units and formats — then back-checks that nothing was ' +
      'silently lost.',
    capabilities: [
      'Source register and intent analysis',
      'Terminology and glossary management',
      'Translation and cultural adaptation',
      'Back-translation quality review',
    ],
    team: {
      analysis: {
        name: 'Source Text Analyst',
        description: 'Reads the source for register, intent and hidden traps.',
      },
      terminology: {
        name: 'Terminology Specialist',
        description: 'Builds the glossary and the do-not-translate list.',
      },
      localizer: {
        name: 'Translator & Localizer',
        description: 'Produces the translated and adapted text.',
      },
      review: {
        name: 'Translation Reviewer',
        description: 'Back-checks meaning, consistency and completeness.',
      },
    },
  },
  climate: {
    name: 'Climate & Sustainability Analyst',
    description:
      'Sets the system boundary, builds the emissions and resource inventory, ' +
      'benchmarks it like for like, and ranks reduction levers by abatement ' +
      'per unit cost.',
    capabilities: [
      'System boundary and scope definition',
      'Emissions and resource inventory',
      'Like-for-like benchmarking',
      'Abatement lever ranking',
    ],
    team: {
      scope: {
        name: 'System Boundary Analyst',
        description:
          'Defines what is counted, what is excluded, and in which scope.',
      },
      inventory: {
        name: 'Inventory Analyst',
        description: 'Collects the actual figures with units, year and source.',
      },
      benchmarks: {
        name: 'Benchmarking Analyst',
        description:
          'Compares against standard, peer and trajectory, like for like.',
      },
      levers: {
        name: 'Abatement Lever Analyst',
        description: 'Ranks reduction options and separates offsets from cuts.',
      },
      assessment: {
        name: 'Sustainability Assessment Lead',
        description:
          'States the position, the credible path, and the honest claim.',
      },
    },
  },
};

/** Return a copy of a builtin agent with the catalog UI copy applied. */
export function localizeBuiltinAgent(agent: BuiltinAgent): BuiltinAgent {
  const locale = AGENT_LOCALE[agent.domain];
  if (!locale) return agent;
  return {
    ...agent,
    name: locale.name,
    description: locale.description,
    capabilities: locale.capabilities,
    team: agent.team.map((member) => ({
      ...member,
      ...(locale.team[member.id] ?? {}),
    })),
  };
}

/**
 * One-liner for a subagent tool-activity event. Action ids match the
 * backend tool catalog; unknown actions fall back to the raw `content`.
 */
export function describeSubagentActivity(event: AgentEvent): string {
  switch (event.action) {
    case 'web_search':
      return `Web search: ${event.query ?? ''}`.trim();
    case 'data_fetch':
      return `Fetching data: ${event.url ?? ''}`.trim();
    case 'code_execution':
      return 'Running code in sandbox';
    case 'repo_intel':
      return `Reading repository: ${event.repo ?? ''}`.trim();
    case 'social_search':
      return `Searching X: ${event.query ?? ''}`.trim();
    case 'community_read':
      return `Reading community channel: ${event.channel ?? ''}`.trim();
    case 'places_intel':
      return `Looking up places: ${event.query ?? ''}`.trim();
    case 'view_original_request':
      return 'Reading the original request';
    default:
      return event.content ?? '';
  }
}

/** Catalog display name for a team member; falls back to the backend name. */
export function memberDisplayName(
  domain: string | undefined,
  memberId: string | undefined,
  fallback: string,
): string {
  if (!domain || !memberId) return fallback;
  return AGENT_LOCALE[domain]?.team[memberId]?.name ?? fallback;
}
