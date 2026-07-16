import { useState, useEffect, useCallback } from 'react';
import { KnowledgeItem, GraphData, KnowledgeHealth, SkillConfig } from '../types';

export function useKnowledge() {
  const [items, setItems] = useState<KnowledgeItem[]>([]);
  const [graph, setGraph] = useState<GraphData | null>(null);
  const [health, setHealth] = useState<KnowledgeHealth | null>(null);
  const [skills, setSkills] = useState<SkillConfig[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      fetch('/api/knowledge/items?limit=50').then(r => r.json()),
      fetch('/api/knowledge/graph').then(r => r.json()),
      fetch('/api/knowledge/health').then(r => r.json()),
      fetch('/api/knowledge/skills').then(r => r.json()),
    ]).then(([itemsData, graphData, healthData, skillsData]) => {
      setItems(itemsData.items || []);
      setGraph(graphData);
      setHealth(healthData);
      setSkills(skillsData.skills || []);
      setLoading(false);
    }).catch(e => {
      setError(e?.message || String(e));
      setLoading(false);
    });
  }, []);

  useEffect(() => { reload(); }, [reload]);

  return { items, graph, health, skills, loading, error, reload };
}
