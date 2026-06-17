#!/usr/bin/env python3
import os
import sqlite3
import json
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'graph.db')


def _cosine(a, b):
    if a is None or b is None:
        return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


class MemoryAwareness:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute('PRAGMA journal_mode=WAL')
        self._load()

    def _load(self):
        c = self.conn.cursor()
        c.execute('SELECT id, content, embedding, importance, tier, confidence, verified, access_count, tags FROM nodes')
        self.nodes = []
        for r in c.fetchall():
            emb = np.array(json.loads(r[2])) if r[2] else None
            self.nodes.append({
                'id': r[0], 'content': r[1], 'embedding': emb,
                'importance': r[3], 'tier': r[4], 'confidence': r[5] or 0.5,
                'verified': r[6] or 0, 'access_count': r[7] or 0, 'tags': r[8] or ''
            })

        c.execute('SELECT source_id, target_id, weight FROM edges')
        self.edges = [(r[0], r[1], r[2]) for r in c.fetchall()]

        self.by_tier = defaultdict(list)
        for n in self.nodes:
            self.by_tier[n['tier']].append(n)

    def _freshness_score(self, node):
        """Calculate freshness score (0-1) based on last update time.
        1.0 = updated today, 0.5 = 30 days ago, 0.0 = 180+ days ago."""
        try:
            updated = node.get('updated_at') or node.get('created_at')
            if not updated:
                return 0.5
            dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
            days = (datetime.utcnow() - dt.replace(tzinfo=None)).days
            return max(0.0, 1.0 - days / 180.0)
        except Exception:
            return 0.5

    def assess(self, query, top_k=10):
        query_words = set(query.lower().split())
        scored = []
        for n in self.nodes:
            content_words = set(n['content'].lower().split())
            overlap = len(query_words & content_words)
            if overlap > 0:
                freshness = self._freshness_score(n)
                score = overlap / len(query_words) * n['importance'] * (n['confidence'] or 0.5) * (0.5 + 0.5 * freshness)
                scored.append((score, n))

        scored.sort(key=lambda x: -x[0])
        top = scored[:top_k]

        if not scored:
            coverage = 0.0
        else:
            max_possible = len(query_words) * 1.0 * 1.0
            actual = sum(s for s, _ in top)
            coverage = min(1.0, actual / max_possible)

        avg_confidence = np.mean([n['confidence'] for _, n in top]) if top else 0.0
        verified_count = sum(1 for _, n in top if n['verified'])
        avg_freshness = np.mean([self._freshness_score(n) for _, n in top]) if top else 0.0

        found_words = set()
        for _, n in top:
            found_words.update(n['content'].lower().split())
        gaps = [w for w in query_words if w not in found_words and len(w) > 3]

        tier_dist = defaultdict(int)
        for _, n in top:
            tier_dist[n['tier']] += 1

        # Determine if agent should admit ignorance
        should_admit_ignorance = coverage < 0.3 or (avg_confidence < 0.4 and verified_count == 0)

        return {
            'coverage': round(coverage, 2),
            'avg_confidence': round(avg_confidence, 2),
            'avg_freshness': round(avg_freshness, 2),
            'verified_count': verified_count,
            'total_relevant': len(scored),
            'should_admit_ignorance': should_admit_ignorance,
            'top_facts': [(n['content'][:80], n['confidence'], n['tier']) for _, n in top[:5]],
            'gaps': gaps[:5],
            'tier_distribution': dict(tier_dist),
            'total_nodes': len(self.nodes),
            'total_edges': len(self.edges),
        }

    def get_stats(self):
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) FROM nodes')
        total = c.fetchone()[0]
        c.execute('SELECT tier, COUNT(*) FROM nodes GROUP BY tier')
        tiers = dict(c.fetchall())
        c.execute('SELECT source_type, COUNT(*) FROM nodes GROUP BY source_type')
        sources = dict(c.fetchall())
        c.execute('SELECT COUNT(*) FROM edges')
        edges = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM nodes WHERE verified=1')
        verified = c.fetchone()[0]
        c.execute('SELECT ROUND(AVG(confidence),2) FROM nodes')
        avg_conf = c.fetchone()[0]

        return {
            'total_nodes': total,
            'total_edges': edges,
            'tiers': tiers,
            'sources': sources,
            'verified': verified,
            'avg_confidence': avg_conf,
        }

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    ma = MemoryAwareness()

    print('=== MEMORY STATS ===')
    stats = ma.get_stats()
    for k, v in stats.items():
        print(f'  {k}: {v}')

    print('\n=== ASSESSMENT: архитектура системы ===')
    report = ma.assess('архитектура системы')
    for k, v in report.items():
        if k != 'top_facts':
            print(f'  {k}: {v}')

    print('\n  Top facts:')
    for fact, conf, tier in report['top_facts']:
        print(f'    [tier={tier}, conf={conf:.1f}] {fact}')

    ma.close()
