#!/usr/bin/env python3
import sys, os, json, sqlite3, numpy as np
from datetime import datetime
from collections import defaultdict

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'graph.db')
LOG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'consolidation.log')
SIMILARITY_THRESHOLD = 0.92
WEAK_EDGE_THRESHOLD = 0.2
STRONG_EDGE_THRESHOLD = 0.7

def log(msg):
    ts = datetime.now().isoformat()
    line = f'[{ts}] {msg}'
    print(line)
    with open(LOG_PATH, 'a') as f:
        f.write(line + '\n')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA journal_mode=WAL')
    return conn

def load_nodes(conn):
    c = conn.cursor()
    c.execute('SELECT id, content, embedding, importance, tier, confidence, access_count, tags FROM nodes')
    nodes = []
    for row in c.fetchall():
        emb = np.array(json.loads(row[2])) if row[2] else None
        nodes.append({'id': row[0], 'content': row[1], 'embedding': emb, 'importance': row[3], 'tier': row[4], 'confidence': row[5], 'access_count': row[6] or 0, 'tags': row[7] or ''})
    return nodes

def load_edges(conn):
    c = conn.cursor()
    c.execute('SELECT id, source_id, target_id, weight, edge_type FROM edges')
    return [{'id': r[0], 'source_id': r[1], 'target_id': r[2], 'weight': r[3], 'edge_type': r[4]} for r in c.fetchall()]

def cosine_sim(a, b):
    if a is None or b is None: return 0.0
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    if na == 0 or nb == 0: return 0.0
    return float(np.dot(a, b) / (na * nb))

def find_duplicates(nodes):
    pairs = []
    for i in range(len(nodes)):
        for j in range(i+1, len(nodes)):
            sim = cosine_sim(nodes[i]['embedding'], nodes[j]['embedding'])
            if sim >= SIMILARITY_THRESHOLD:
                pairs.append((i, j, sim))
    pairs.sort(key=lambda x: -x[2])
    return pairs

def merge_nodes(conn, a, b, sim):
    c = conn.cursor()
    if len(b['content']) > len(a['content']):
        c.execute('UPDATE nodes SET content=?, version=version+1, updated_at=? WHERE id=?', (b['content'], datetime.now().isoformat(), a['id']))
    tags_a = set(a['tags'].split(',')) if a['tags'] else set()
    tags_b = set(b['tags'].split(',')) if b['tags'] else set()
    all_tags = tags_a | tags_b
    if all_tags:
        c.execute('UPDATE nodes SET tags=? WHERE id=?', (','.join(sorted(all_tags)), a['id']))
    c.execute('UPDATE nodes SET access_count=access_count+? WHERE id=?', (b['access_count'], a['id']))
    c.execute('UPDATE nodes SET importance=?, confidence=? WHERE id=?', (max(a['importance'], b['importance']), max(a['confidence'] or 0.5, b['confidence'] or 0.5), a['id']))
    c.execute('UPDATE edges SET source_id=? WHERE source_id=? AND target_id!=?', (a['id'], b['id'], a['id']))
    c.execute('UPDATE edges SET target_id=? WHERE target_id=? AND source_id!=?', (a['id'], b['id'], a['id']))
    c.execute('DELETE FROM nodes WHERE id=?', (b['id'],))
    c.execute('DELETE FROM node_embeddings WHERE node_id=?', (b['id'],))
    log(f'  Merged: {b["content"][:50]}... -> {a["content"][:50]}... (sim={sim:.2f})')

def remove_weak_edges(conn, edges):
    c = conn.cursor()
    removed = 0
    for e in edges:
        if e['weight'] < WEAK_EDGE_THRESHOLD:
            c.execute('DELETE FROM edges WHERE id=?', (e['id'],))
            removed += 1
    return removed

def strengthen_edges(conn, nodes, edges):
    c = conn.cursor()
    node_map = {n['id']: n for n in nodes}
    strengthened = 0
    for e in edges:
        src = node_map.get(e['source_id'])
        tgt = node_map.get(e['target_id'])
        if src and tgt and src['tier']==tgt['tier'] and e['weight']>=STRONG_EDGE_THRESHOLD:
            nw = min(1.0, e['weight']*1.1)
            c.execute('UPDATE edges SET weight=?, updated_at=? WHERE id=?', (nw, datetime.now().isoformat(), e['id']))
            strengthened += 1
    return strengthened

def update_tiers(conn, nodes):
    c = conn.cursor()
    ec = defaultdict(int)
    for r in c.execute('SELECT source_id FROM edges'): ec[r[0]] += 1
    for r in c.execute('SELECT target_id FROM edges'): ec[r[0]] += 1
    updated = 0
    for n in nodes:
        cnt = ec.get(n['id'], 0)
        old = n['tier']
        if n['importance']>=0.9 or cnt>=5: nt=1
        elif n['importance']>=0.7 or cnt>=3: nt=2
        elif n['importance']<0.3 and cnt<=1: nt=4
        else: nt=3
        if nt!=old:
            c.execute('UPDATE nodes SET tier=? WHERE id=?', (nt, n['id']))
            updated += 1
    return updated

def run_consolidation(dry_run=False):
    log('=== Consolidation start ===')
    conn = get_db()
    nodes = load_nodes(conn)
    edges = load_edges(conn)
    log(f'  Nodes: {len(nodes)}, Edges: {len(edges)}')

    duplicates = find_duplicates(nodes)
    log(f'  Duplicates found: {len(duplicates)}')
    merged = 0
    if not dry_run:
        for i, j, sim in duplicates:
            na, nb = nodes[i], nodes[j]
            c = conn.cursor()
            c.execute('SELECT id FROM nodes WHERE id=?', (na['id'],))
            if not c.fetchone(): continue
            c.execute('SELECT id FROM nodes WHERE id=?', (nb['id'],))
            if not c.fetchone(): continue
            merge_nodes(conn, na, nb, sim)
            merged += 1
        conn.commit()
        log(f'  Merged: {merged}')
        nodes = load_nodes(conn)
        edges = load_edges(conn)

    weak = len([e for e in edges if e['weight']<WEAK_EDGE_THRESHOLD])
    log(f'  Weak edges: {weak}')
    removed = 0 if dry_run else remove_weak_edges(conn, edges)
    if not dry_run: conn.commit()

    strong = len([e for e in edges if e['weight']>=STRONG_EDGE_THRESHOLD])
    log(f'  Strong edges: {strong}')
    strengthened = 0 if dry_run else strengthen_edges(conn, nodes, edges)
    if not dry_run: conn.commit()

    tier_upd = 0 if dry_run else update_tiers(conn, nodes)
    if not dry_run: conn.commit()

    # Verification step: promote high-confidence unverified facts
    log('  Verification: checking unverified facts...')
    c = conn.cursor()
    c.execute('SELECT id, confidence, importance FROM nodes WHERE verified=0 AND confidence > 0.8')
    to_verify = c.fetchall()
    verified_count = 0
    if not dry_run:
        for node_id, conf, imp in to_verify:
            c.execute('UPDATE nodes SET verified=1, updated_at=? WHERE id=?',
                      (datetime.now().isoformat(), node_id))
            verified_count += 1
        conn.commit()
    log(f'  Verified: {verified_count} facts promoted (confidence > 0.8)')

    c = conn.cursor()
    c.execute('SELECT tier, COUNT(*) FROM nodes GROUP BY tier ORDER BY tier')
    tiers = c.fetchall()
    c.execute('SELECT COUNT(*) FROM edges')
    te = c.fetchone()[0]
    c.execute('SELECT COUNT(*) FROM nodes')
    tn = c.fetchone()[0]
    log(f'  Final: {tn} nodes, {te} edges')
    for t, cnt in tiers:
        log(f'    Tier {t}: {cnt}')
    conn.close()
    log('=== Consolidation done ===')
    return {'duplicates': len(duplicates), 'merged': merged, 'weak_removed': removed, 'strengthened': strengthened, 'tiers_updated': tier_upd, 'nodes': tn, 'edges': te}

if __name__ == '__main__':
    dry_run = '--dry-run' in sys.argv
    result = run_consolidation(dry_run=dry_run)
    print(f'\nDuplicates: {result["duplicates"]}, Merged: {result["merged"]}, Weak removed: {result["weak_removed"]}, Strengthened: {result["strengthened"]}, Tiers: {result["tiers_updated"]}, Nodes: {result["nodes"]}, Edges: {result["edges"]}')
