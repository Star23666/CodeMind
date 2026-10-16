"""Local deployment smoke test. Uses fictional data and removes its own test user."""
import secrets
import time
import httpx
from sqlalchemy import text
from app.db.session import SessionLocal
from app.core.config import settings


def run():
    user_id = None
    document_id = None
    finished_ingestion = False
    username = 'smoke_' + secrets.token_hex(6)
    password = secrets.token_urlsafe(24)
    with httpx.Client(base_url='http://127.0.0.1:8000/api', timeout=100) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code >= 400:
                print('HTTP_ERROR', path, response.status_code)
            response.raise_for_status()
            return response.json()

        try:
            user = request('POST', '/auth/register', json={
                'username': username, 'email': username + '@example.invalid', 'password': password})
            user_id = user['id']
            token = request('POST', '/auth/login', json={'username': username, 'password': password})
            client.headers['Authorization'] = 'Bearer ' + token['access_token']
            print('REGISTER_LOGIN_OK', flush=True)
            bases = request('GET', '/knowledge-bases')
            kb = next(item for item in bases if item['owner_id'] == user_id)
            sample = '# 虚构部署测试资料\n本资料仅用于软件测试，不代表真实企业。\n星河演示公司的技术咨询服务时间为工作日09:00至18:00。\n提交报障时需要软件名称、版本号、错误截图和复现步骤。\n报价、退款、赔偿与交付日期由人工确认，不能由AI直接承诺。\n'
            document = request('POST', '/documents/upload', data={'knowledge_base_id': str(kb['id'])},
                files={'file': ('deployment-smoke.txt', sample.encode('utf-8'), 'text/plain')})
            document_id = document['id']
            for _ in range(90):
                document = request('GET', f'/documents/{document_id}')
                state = document['parse_status']
                if state in ('completed', 'failed', 'cancelled'):
                    finished_ingestion = True
                    break
                time.sleep(1)
            assert document['parse_status'] == 'completed', document['parse_status']
            print('UPLOAD_INGEST_OK', flush=True)
            query = {'knowledge_base_id': kb['id'], 'query': '技术咨询服务时间是什么？',
                     'enable_rewrite': False, 'enable_rerank': False, 'score_threshold': 0.45}
            found = request('POST', '/search', json=query)
            assert found['results'], 'No retrieval results'
            assert any('18:00' in item['source_text'] for item in found['results'])
            print('RETRIEVAL_OK', flush=True)
            if settings.llm_api_key:
                answer = request('POST', '/chat', json={
                    'knowledge_base_id': kb['id'], 'question': '技术咨询服务时间是什么？',
                    'enable_rewrite': False, 'enable_rerank': False, 'score_threshold': 0.45})
                print('CHAT_RESPONSE', answer, flush=True)
            else:
                print('CHAT_SKIPPED_MISSING_KEY', flush=True)
        finally:
            # Only delete data created by this invocation; retain on unfinished ingestion.
            if user_id and (document_id is None or finished_ingestion):
                if document_id:
                    request('DELETE', f'/documents/{document_id}')
                with SessionLocal() as db:
                    db.execute(text('DELETE FROM users WHERE id=:id AND username=:name'),
                               {'id': user_id, 'name': username})
                    db.commit()
                print('OWN_TEST_DATA_CLEANED', flush=True)


if __name__ == '__main__':
    run()
