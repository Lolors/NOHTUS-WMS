# 모바일 앱을 같은 도메인(/mobile/)에서 열기

현재 구조:

- 웹(Streamlit): `streamlit run app.py` → 기본 8501 포트
- 모바일(FastAPI): `nohtus.mobile_api.main` → 8535 포트, `mobile_app/` 정적 파일 + `/api/*` 제공

이 둘을 `https://nohtus-wms.online/` 하나의 도메인에서, 모바일은
`https://nohtus-wms.online/mobile/` 경로로 열리도록 하려면 두 가지가 필요하다.

## 1. 앱 쪽 변경 (이미 이 브랜치에 반영됨)

- `mobile_app/app.js`: `API_BASE`를 하드코딩된 `""` 대신 현재 페이지 경로에서
  계산하도록 수정. `/mobile/`에서 열든 프리픽스 없이 열든 `fetch`가 항상 같은
  prefix 밑으로 나간다.
- `mobile_app/sw.js`: API 요청을 캐시에서 제외하는 조건을 `startsWith("/api/")`
  에서 `includes("/api/")`로 변경. `/mobile/api/...` 형태에서도 재고 데이터가
  캐시되지 않도록.
- `nohtus/mobile_api/main.py`: 기존 `app`(프리픽스 없음, 로컬 개발용)은 그대로
  두고, `/mobile`과 `/` 양쪽에 동일한 API를 얹은 `root_app`을 추가.
  **운영 서버에서는 `app` 대신 `root_app`을 띄워야 한다.**

운영 서버에서 모바일 백엔드 실행 명령:

```bash
python -m uvicorn nohtus.mobile_api.main:root_app --port 8535
```

(기존 `nohtus.mobile_api.main:app`도 여전히 동작하지만, 그건 프리픽스 없이
호스트에 바로 붙을 때만 쓰는 로컬 개발용이다.)

## 2. Cloudflare Tunnel 쪽 변경 (서버에서 직접 해야 함)

이 세션은 git 리포지토리만 다룰 수 있고 실제 운영 서버에 SSH로 접속되어 있지
않다. 아래 설정은 서버에서 직접 적용해야 한다.

`cloudflared`의 `config.yml`에서 같은 hostname에 대해 **path 조건이 있는
규칙을 먼저**, 그 다음에 일반 규칙을 두면 된다 (cloudflared는 위에서부터
순서대로 매칭하고 처음 매칭된 규칙을 사용한다):

```yaml
tunnel: <TUNNEL_ID>
credentials-file: /etc/cloudflared/<TUNNEL_ID>.json

ingress:
  # 모바일: /mobile 이하 경로만 FastAPI(8535)로
  - hostname: nohtus-wms.online
    path: ^/mobile(/.*)?$
    service: http://localhost:8535

  # 나머지는 기존 웹(Streamlit, 8501)으로
  - hostname: nohtus-wms.online
    service: http://localhost:8501

  - service: http_status:404
```

주의:

- Cloudflare Tunnel은 경로를 벗겨내지 않고(prefix strip 없이) 원래 경로
  그대로(`/mobile/api/login` 등) origin으로 넘긴다. 그래서 FastAPI 쪽도
  `/mobile` 프리픽스를 스스로 이해해야 하고, 그게 위 1번의 `root_app`이 하는
  역할이다.
- `cloudflared` 버전이 오래되면 ingress 규칙에 `path` 필드를 지원하지 않을 수
  있다 (`cloudflared --version`으로 확인, 2022년 이후 버전이면 대부분 지원).
  지원하지 않는 버전이면 `cloudflared`를 업데이트하거나, 서버에 로컬 nginx/
  Caddy를 하나 더 두고 그쪽에서 `/mobile` 프리픽스로 두 백엔드를 나눈 뒤
  Cloudflare Tunnel은 그 nginx/Caddy 하나만 바라보게 하는 방법도 있다.
- 설정 반영 후 `cloudflared`를 재시작해야 한다
  (예: `sudo systemctl restart cloudflared`, 또는 사용 중인 실행 방식에 맞게).

## 3. 확인

1. 서버에서 `uvicorn nohtus.mobile_api.main:root_app --port 8535` 로 모바일
   백엔드를 띄운다 (기존 8501 Streamlit은 그대로 둔다).
2. `cloudflared` config를 위 내용으로 갱신하고 재시작한다.
3. 휴대폰에서 `https://nohtus-wms.online/mobile/` 로 접속해 로그인 화면이
   뜨는지, 로그인 후 재고 검색이 정상 동작하는지 확인한다.
4. PC 브라우저에서 `https://nohtus-wms.online/` (웹, Streamlit)도 그대로
   동작하는지 함께 확인한다.
