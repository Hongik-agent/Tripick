import { createClient } from "@supabase/supabase-js"

const url = import.meta.env.VITE_SUPABASE_URL
const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY

// 공개 가능한 프로젝트 키만 브라우저에 넣습니다. service_role/secret 키는 절대 사용하지 마세요.
// 환경 변수가 없으면 앱은 실행하되 로그인을 시작할 수 없습니다.
export const supabase =
  url && publishableKey ? createClient(url, publishableKey) : null
