#!/usr/bin/env python3
import os, sys, json, sqlite3, urllib.request, urllib.parse
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IKKF_API = 'http://127.0.0.1:8766'
DB_PATH = os.path.join(PROJECT_ROOT, 'data', 'graph.db')


class SkillLearner:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.conn.execute('PRAGMA journal_mode=WAL')

    def search_skill(self, query, limit=5):
        try:
            q = urllib.parse.quote(query[:120])
            url = f'{IKKF_API}/search?q={q}&limit={limit}'
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            results = data.get('results', [])
            skills = []
            for r in results:
                node = r.get('node', r)
                if node.get('node_type') == 'skill' or 'skill' in (node.get('tags') or []):
                    skills.append({'id': node.get('id'), 'name': node.get('content', '')[:100], 'score': r.get('score', 0)})
            return skills
        except Exception:
            return []

    def find_skill_by_name(self, name):
        try:
            q = urllib.parse.quote(name)
            url = f'{IKKF_API}/search?q={q}&limit=3'
            with urllib.request.urlopen(url, timeout=15) as r:
                data = json.loads(r.read())
            for r in data.get('results', []):
                node = r.get('node', r)
                if node.get('node_type') == 'skill':
                    return node
            return None
        except Exception:
            return None

    def create_skill(self, name, steps, source='self', device_profile='macbook_pro_2012'):
        lines = ['Навык: ' + name, 'Шаги:']
        for i, s in enumerate(steps):
            lines.append(f'  {i+1}. {s}')
        content_text = chr(10).join(lines)
        try:
            data = {
                'content': content_text,
                'node_type': 'skill',
                'importance': 0.7,
                'tags': ['skill', name.lower().replace(' ', '_')],
                'source': source,
                'metadata': {
                    'name': name, 'steps': steps, 'source': source,
                    'success_rate': 0.0, 'times_used': 0,
                    'device_profile': device_profile,
                    'created_at': datetime.now().isoformat(),
                }
            }
            url = f'{IKKF_API}/node'
            body = json.dumps(data).encode()
            req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=30) as r:
                result = json.loads(r.read())
            return result.get('id')
        except Exception:
            return None

    def update_skill_usage(self, skill_id, success=True):
        try:
            url = f'{IKKF_API}/node/{skill_id}'
            with urllib.request.urlopen(url, timeout=15) as r:
                node = json.loads(r.read())
            meta = node.get('metadata', {})
            times_used = meta.get('times_used', 0) + 1
            old_rate = meta.get('success_rate', 0.0)
            if success:
                new_rate = min(1.0, old_rate + (1.0 - old_rate) / times_used)
            else:
                new_rate = max(0.0, old_rate - old_rate / times_used)
            meta['times_used'] = times_used
            meta['success_rate'] = round(new_rate, 3)
            meta['last_used'] = datetime.now().isoformat()
            update_url = f'{IKKF_API}/node/{skill_id}'
            body = json.dumps({'metadata': meta}).encode()
            req = urllib.request.Request(update_url, data=body,
                                        headers={'Content-Type': 'application/json'},
                                        method='PUT')
            with urllib.request.urlopen(req, timeout=30) as r:
                json.loads(r.read())
            return True
        except Exception:
            return False

    def get_or_learn(self, task_description):
        skills = self.search_skill(task_description)
        if skills and skills[0]['score'] > 0.1:
            best = skills[0]
            return {'found': True, 'skill_id': best['id'], 'name': best['name'], 'score': best['score']}
        name = task_description.split()[0] if task_description else 'unknown'
        existing = self.find_skill_by_name(name)
        if existing:
            return {'found': True, 'skill_id': existing.get('id'), 'name': existing.get('content', '')[:100], 'score': 0.5}
        steps = [
            'Анализировать задачу: ' + task_description[:100],
            'Определить необходимые инструменты',
            'Выполнить по шагам',
            'Проверить результат',
        ]
        skill_id = self.create_skill(name, steps, source='self')
        if skill_id:
            return {'found': False, 'skill_id': skill_id, 'name': name, 'score': 0.0, 'created': True}
        return {'found': False, 'error': 'Failed to create skill'}

    def close(self):
        self.conn.close()


if __name__ == '__main__':
    learner = SkillLearner()
    print('=== Skill Learner Test ===')
    result = learner.get_or_learn('настройка nginx')
    print('Result:', json.dumps(result, ensure_ascii=False, indent=2))
    c = learner.conn.cursor()
    c.execute("SELECT COUNT(*) FROM nodes WHERE node_type='skill'")
    print('Total skills in IKKF:', c.fetchone()[0])
    learner.close()
