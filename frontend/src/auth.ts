import { api } from "./api"

export async function login(provider: "google" | "kakao", returnTo: string) {
  const result = await api<{ url: string }>("/auth/login/" + provider, {
    method: "POST",
    body: JSON.stringify({ returnTo }),
  })
  location.assign(result.url)
}
