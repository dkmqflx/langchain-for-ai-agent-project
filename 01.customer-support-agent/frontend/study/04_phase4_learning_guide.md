# Phase 4 학습 가이드 — 관리자 문서 업로드 화면

**목표**: PDF/TXT 업로드 → RAG 인덱싱, 업로드된 문서 목록 표시. **스트리밍 없음 — 단순 폼.**

> 난이도 낮음. Phase 2~3의 스트리밍/data-part 복잡도에서 벗어나 일반 폼 + 목록 CRUD를 익히는 단계.

---

## 학습 흐름도

```
app/admin/documents/page.tsx
   ├── 파일 선택 + 업로드 폼 → POST /upload (multipart/form-data) → RAG 인덱싱
   └── GET /documents → 업로드된 문서 목록 테이블
```

---

## Step 1: 파일 업로드는 JSON이 아니라 multipart (10분)

> ⚠️ 주의: 업로드는 `multipart/form-data`라 **`lib/api.ts`의 `apiFetch`(JSON 전용)를 그대로 쓰면 안 됩니다.**
> `apiFetch`는 `Content-Type: application/json`을 강제하므로, 업로드는 별도 처리하거나 헤더를 비워야 합니다.

```ts
const form = new FormData();
form.append("file", file);                 // <input type="file">에서 받은 File

const res = await fetch(`${API_BASE_URL}/upload`, {
  method: "POST",
  body: form,                              // Content-Type을 직접 지정하지 말 것
});                                         // 브라우저가 boundary 포함해 자동 설정
const json = await res.json();             // { data, isSuccess, code, message } 봉투
```
- **함정**: `FormData`를 보낼 때 `Content-Type`을 수동으로 넣으면 boundary가 빠져 깨집니다. 헤더를 비워 브라우저에 맡기세요.
- 봉투 처리는 동일(`isSuccess`/`code`/`message`).

### 학습 질문
- [ ] 왜 파일 업로드는 JSON이 아니라 multipart인가?
- [ ] `apiFetch`를 재사용하려면 무엇을 수정해야 하나? (헤더 강제 부분을 옵션화)

---

## Step 2: 문서 목록 (GET /documents) (5분)

```ts
import { apiFetch } from "@/lib/api";
const data = await apiFetch<{ documents: { source: string; chunks?: number }[] }>("/documents");
```
- 응답 형태(필드명)는 백엔드 `routers/upload.py`의 `GET /documents` 응답 모델로 확인.
- shadcn `Card`/테이블(이미 설치된 `components/ui/*`)로 목록 렌더.

---

## Step 3: 진행/성공/실패 상태 표시 (5분)

- 업로드 중: 버튼 비활성화 + 스피너(`components/ui/spinner.tsx`).
- 성공/실패: shadcn `Alert` 또는 토스트 패턴으로 안내.
- 성공 시 목록을 다시 불러와(refetch) 새 문서가 보이게.

---

## 검증

- [ ] PDF 업로드 → 성공 응답 → 목록에 나타남.
- [ ] 업로드한 문서 내용을 채팅(`/`)에서 질문 → RAG 검색으로 답변됨(Phase 2와 연결).
- [ ] 잘못된 확장자 업로드 → 백엔드 400 → 안내 메시지 표시.

---

## 검증 체크리스트 (개념)
- [ ] multipart 업로드와 JSON 요청의 차이를 안다.
- [ ] `FormData`에 `Content-Type`을 수동 지정하면 안 되는 이유를 안다.
- [ ] 업로드 → 목록 refetch 흐름을 안다.

---

## 커밋
```
feat(frontend): admin document upload + list
```

## 다음 단계
- **Phase 5**: 관리자 환불 승인 큐.
