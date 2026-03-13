import { useEffect, useState } from 'react';
import './FlowChart.css';

const PIPELINES = {
  simple: {
    nodes: [
      { id: 'query', label: 'Query' },
      { id: 'embed', label: 'Embed' },
      { id: 'search', label: 'Search Tweets' },
      { id: 'top_k', label: 'Top 7' },
      { id: 'llm', label: 'LLM Synthesize' },
      { id: 'answer', label: 'Answer' },
    ],
    edges: [
      ['query', 'embed'],
      ['embed', 'search'],
      ['search', 'top_k'],
      ['top_k', 'llm'],
      ['llm', 'answer'],
    ],
    layout: 'linear',
  },
  agent: {
    nodes: [
      { id: 'query', label: 'Query' },
      { id: 'think', label: 'LLM Think' },
      { id: 'choose', label: 'Choose Tool' },
      { id: 'execute', label: 'Execute' },
      { id: 'observe', label: 'Observe' },
      { id: 'answer', label: 'Answer' },
    ],
    edges: [
      ['query', 'think'],
      ['think', 'choose'],
      ['choose', 'execute'],
      ['execute', 'observe'],
      ['observe', 'think'],
      ['think', 'answer'],
    ],
    layout: 'loop',
  },
  graph: {
    nodes: [
      { id: 'query', label: 'Query' },
      { id: 'page_lookup', label: 'Page Lookup' },
      { id: 'router', label: 'Router' },
      { id: 'tweet_agent', label: 'Tweet Agent' },
      { id: 'news_agent', label: 'News Agent' },
      { id: 'both', label: 'Both Agents' },
      { id: 'answer', label: 'Answer' },
    ],
    edges: [
      ['query', 'page_lookup'],
      ['page_lookup', 'router'],
      ['router', 'tweet_agent'],
      ['router', 'news_agent'],
      ['router', 'both'],
      ['tweet_agent', 'answer'],
      ['news_agent', 'answer'],
      ['both', 'answer'],
    ],
    layout: 'branching',
  },
};

// The sequence of nodes to animate through while loading
const LOADING_SEQUENCES = {
  simple: ['query', 'embed', 'search', 'top_k', 'llm', 'answer'],
  agent: ['query', 'think', 'choose', 'execute', 'observe', 'think', 'choose', 'execute', 'observe', 'think', 'answer'],
  graph: ['query', 'page_lookup', 'router'],
};

function getCompletedPath(mode, graphData, agentData) {
  if (mode === 'simple') {
    return ['query', 'embed', 'search', 'top_k', 'llm', 'answer'];
  }
  if (mode === 'agent') {
    return ['query', 'think', 'choose', 'execute', 'observe', 'think', 'answer'];
  }
  if (mode === 'graph' && graphData) {
    const base = ['query', 'page_lookup', 'router'];
    const route = graphData.route;
    if (route === 'tweet_agent') return [...base, 'tweet_agent', 'answer'];
    if (route === 'news_agent') return [...base, 'news_agent', 'answer'];
    if (route === 'both') return [...base, 'both', 'answer'];
    return base;
  }
  return [];
}

function FlowChart({ mode, loading, graphData, agentData, done, streamNode }) {
  const [activeNode, setActiveNode] = useState(null);
  const [animatedNodes, setAnimatedNodes] = useState(new Set());
  const [completedPath, setCompletedPath] = useState([]);

  const pipeline = PIPELINES[mode];

  // For graph mode: use real SSE streamNode instead of timer animation
  useEffect(() => {
    if (mode === 'graph' && loading && streamNode) {
      setActiveNode(streamNode);
      setAnimatedNodes(prev => new Set([...prev, streamNode]));
    }
  }, [streamNode, mode, loading]);

  // For non-graph modes: timer-based animation
  useEffect(() => {
    if (mode === 'graph') return; // graph uses streamNode
    if (!loading) return;

    setCompletedPath([]);
    setAnimatedNodes(new Set());
    setActiveNode(null);

    const sequence = LOADING_SEQUENCES[mode];
    let step = 0;

    setActiveNode(sequence[0]);
    setAnimatedNodes(new Set([sequence[0]]));
    step = 1;

    const interval = setInterval(() => {
      if (step < sequence.length) {
        const node = sequence[step];
        setActiveNode(node);
        setAnimatedNodes(prev => new Set([...prev, node]));
        step++;
      }
      if (step >= sequence.length && mode === 'agent') {
        step = 1;
        setAnimatedNodes(new Set(['query']));
      }
    }, mode === 'agent' ? 1200 : 800);

    return () => clearInterval(interval);
  }, [loading, mode]);

  // Reset state when loading starts
  useEffect(() => {
    if (loading) {
      setCompletedPath([]);
      setAnimatedNodes(new Set());
      setActiveNode(null);
    }
  }, [loading]);

  // When done, show the completed path
  useEffect(() => {
    if (done && !loading) {
      const path = getCompletedPath(mode, graphData, agentData);
      setCompletedPath(path);
      setActiveNode(null);
      setAnimatedNodes(new Set());
    }
  }, [done, loading, mode, graphData, agentData]);

  const isNodeActive = (nodeId) => activeNode === nodeId;
  const isNodeVisited = (nodeId) => animatedNodes.has(nodeId);
  const isNodeCompleted = (nodeId) => completedPath.includes(nodeId);

  const isEdgeActive = (from, to) => {
    if (loading) {
      return animatedNodes.has(from) && animatedNodes.has(to);
    }
    if (done) {
      const fi = completedPath.indexOf(from);
      const ti = completedPath.indexOf(to);
      return fi !== -1 && ti !== -1 && ti === fi + 1;
    }
    return false;
  };

  const getNodeClass = (nodeId) => {
    const classes = ['flow-node'];
    if (isNodeActive(nodeId)) classes.push('active');
    else if (isNodeVisited(nodeId)) classes.push('visited');

    if (isNodeCompleted(nodeId)) classes.push('completed');

    // Dim unselected branches when done in graph mode
    if (done && mode === 'graph' && completedPath.length > 0) {
      const branchNodes = ['tweet_agent', 'news_agent', 'both'];
      if (branchNodes.includes(nodeId) && !completedPath.includes(nodeId)) {
        classes.push('dimmed');
      }
    }

    return classes.join(' ');
  };

  if (pipeline.layout === 'linear') {
    return (
      <div className="flow-container">
        <div className="flow-linear">
          {pipeline.nodes.map((node, i) => (
            <div key={node.id} className="flow-step">
              <div className={getNodeClass(node.id)}>
                {node.label}
              </div>
              {i < pipeline.nodes.length - 1 && (
                <div className={`flow-arrow ${isEdgeActive(pipeline.nodes[i].id, pipeline.nodes[i + 1].id) ? 'active' : ''}`}>
                  <svg width="44" height="20" viewBox="0 0 44 20">
                    <line x1="0" y1="10" x2="34" y2="10" stroke="currentColor" strokeWidth="2" />
                    <polygon points="34,5 44,10 34,15" fill="currentColor" />
                  </svg>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (pipeline.layout === 'loop') {
    const mainNodes = pipeline.nodes.filter(n => n.id !== 'answer');
    return (
      <div className="flow-container">
        <div className="flow-loop">
          <div className="flow-loop-main">
            {mainNodes.map((node, i) => (
              <div key={node.id} className="flow-step">
                <div className={getNodeClass(node.id)}>
                  {node.label}
                </div>
                {i < mainNodes.length - 1 && (
                  <div className={`flow-arrow ${isEdgeActive(mainNodes[i].id, mainNodes[i + 1].id) ? 'active' : ''}`}>
                    <svg width="44" height="20" viewBox="0 0 44 20">
                      <line x1="0" y1="10" x2="34" y2="10" stroke="currentColor" strokeWidth="2" />
                      <polygon points="34,5 44,10 34,15" fill="currentColor" />
                    </svg>
                  </div>
                )}
              </div>
            ))}
          </div>
          <div className="flow-loop-back">
            <svg className={`loop-arrow-svg ${isEdgeActive('observe', 'think') ? 'active' : ''}`} viewBox="0 0 100 30" preserveAspectRatio="none">
              <path d="M90,5 Q95,15 90,25 L10,25 Q5,15 10,5" fill="none" stroke="currentColor" strokeWidth="2" strokeDasharray="4,3" />
              <polygon points="12,2 6,8 16,8" fill="currentColor" />
            </svg>
          </div>
          <div className="flow-loop-exit">
            <div className={`flow-arrow vertical ${isEdgeActive('think', 'answer') ? 'active' : ''}`}>
              <svg width="20" height="28" viewBox="0 0 20 28">
                <line x1="10" y1="0" x2="10" y2="20" stroke="currentColor" strokeWidth="2" />
                <polygon points="5,20 10,28 15,20" fill="currentColor" />
              </svg>
            </div>
            <div className={getNodeClass('answer')}>
              Answer
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Branching layout for graph mode — vertical for sidebar
  if (pipeline.layout === 'branching') {
    const branches = [
      { id: 'tweet_agent', label: 'Tweet Agent' },
      { id: 'news_agent', label: 'News Agent' },
      { id: 'both', label: 'Both Agents' },
    ];

    const vertArrow = (from, to) => (
      <div className={`flow-arrow vertical ${isEdgeActive(from, to) ? 'active' : ''}`}>
        <svg width="20" height="24" viewBox="0 0 20 24">
          <line x1="10" y1="0" x2="10" y2="16" stroke="currentColor" strokeWidth="2" />
          <polygon points="5,16 10,24 15,16" fill="currentColor" />
        </svg>
      </div>
    );

    return (
      <div className="flow-container">
        <div className="flow-vertical">
          {/* Query → Page Lookup → Router (vertical) */}
          <div className={getNodeClass('query')}>Query</div>
          {vertArrow('query', 'page_lookup')}
          <div className={getNodeClass('page_lookup')}>Page Lookup</div>
          {vertArrow('page_lookup', 'router')}
          <div className={getNodeClass('router')}>Router</div>

          {/* Branches side by side */}
          <div className="flow-branch-row">
            {branches.map((b) => (
              <div key={b.id} className="flow-branch-col">
                {vertArrow('router', b.id)}
                <div className={getNodeClass(b.id)}>{b.label}</div>
              </div>
            ))}
          </div>

          {/* Merge to answer */}
          <div className={`flow-arrow vertical ${
            isEdgeActive('tweet_agent', 'answer') ||
            isEdgeActive('news_agent', 'answer') ||
            isEdgeActive('both', 'answer') ? 'active' : ''
          }`}>
            <svg width="20" height="24" viewBox="0 0 20 24">
              <line x1="10" y1="0" x2="10" y2="16" stroke="currentColor" strokeWidth="2" />
              <polygon points="5,16 10,24 15,16" fill="currentColor" />
            </svg>
          </div>
          <div className={getNodeClass('answer')}>Answer</div>
        </div>
      </div>
    );
  }

  return null;
}

export default FlowChart;
