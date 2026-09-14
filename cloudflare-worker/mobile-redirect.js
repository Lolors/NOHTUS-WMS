/**
 * nohtus-wms.online 루트("/")에 모바일 기기로 접속하면, 스트림릿(8501)이
 * 로드되기도 전에 Cloudflare 엣지에서 곧바로 /mobile/ 로 302 리다이렉트한다.
 *
 * 기존에는 스트림릿(무거운 SPA)이 다 로드된 뒤 파이썬 코드(nohtus/device.py,
 * nohtus/bootstrap.py)가 모바일인지 판단해서 meta refresh로 다시 리다이렉트했기
 * 때문에, 화면이 한 번 걸렸다 넘어가는 느낌이 있었다. 이 워커는 그 판단을
 * origin에 요청이 가기도 전에 엣지에서 끝내버려서 그 지연을 없앤다.
 *
 * 배포 방법(Cloudflare 대시보드):
 * 1. Workers & Pages → Create → 이 파일 내용을 붙여넣고 배포
 * 2. 해당 zone(도메인)의 Workers Routes에 다음 라우트 추가:
 *      nohtus-wms.online/
 *    (경로 끝에 슬래시 없이 "/*"까지 안 걸어도 됨 — 아래 코드가 path === "/"
 *    인 요청만 처리하고 나머지는 그대로 origin으로 흘려보낸다)
 *
 * PC에서도 모바일 화면을 보고 싶을 때: ?force_desktop=1 을 붙이면 리다이렉트를
 * 건너뛴다(nohtus/device.py의 같은 이름 쿼리 파라미터와 동작을 맞췄다).
 */

const MOBILE_USER_AGENT_RE =
  /android|iphone|ipod|ipad|mobile|windows phone|blackberry|opera mini|iemobile/i;

export default {
  async fetch(request) {
    const url = new URL(request.url);

    const isRoot = url.pathname === "/" || url.pathname === "";
    const forceDesktop = url.searchParams.get("force_desktop") === "1";
    const userAgent = request.headers.get("user-agent") || "";
    const isMobile = MOBILE_USER_AGENT_RE.test(userAgent);

    if (request.method === "GET" && isRoot && isMobile && !forceDesktop) {
      return Response.redirect(`${url.origin}/mobile/`, 302);
    }

    return fetch(request);
  },
};
