// English UI copy for the built-in agent catalog. The backend is fully
// English (LLMs and agents consume it directly); this map provides the
// user-facing names and descriptions, keyed by domain id and member id.

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
