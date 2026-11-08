export type SharedTrip = {
  id: number
  sourceId: number
  owner: string
  publishedAt: number
  likedBy: string[]
  city: string
  country: string
  days: number
  theme: string
  image: string
  en: string
  tag: string
  x: number
  y: number
  places?: string[]
  map?: string
}

export const COMMUNITY_KEY = 'tripick-community-v1'

export function loadCommunity(): SharedTrip[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(COMMUNITY_KEY) || '[]')
    if (!Array.isArray(value)) return []
    return value.filter((post): post is SharedTrip =>
      typeof post === 'object' && post !== null &&
      typeof post.id === 'number' && typeof post.sourceId === 'number' &&
      typeof post.owner === 'string' && typeof post.publishedAt === 'number' &&
      Array.isArray(post.likedBy) && post.likedBy.every((v: unknown) => typeof v === 'string') &&
      typeof post.city === 'string' && typeof post.image === 'string' &&
      typeof post.days === 'number'
    )
  } catch {
    return []
  }
}

export function rankCommunity(posts: SharedTrip[]) {
  return [...posts].sort((a,b) =>
    b.likedBy.length - a.likedBy.length ||
    a.publishedAt - b.publishedAt ||
    a.id - b.id
  )
}

export function Heart({filled=false}:{filled?:boolean}) {
  return <svg width="17" height="17" viewBox="0 0 24 24" fill={filled?'currentColor':'none'} stroke="currentColor" strokeWidth="1.7" aria-hidden="true"><path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z"/></svg>
}

export function CommunityCards({posts,account,onOpen,onHeart}:{posts:SharedTrip[],account:string,onOpen:(post:SharedTrip)=>void,onHeart:(id:number)=>void}) {
  if (!posts.length) return <div className="community-empty"><h3>첫 번째 여행 이야기를 기다리고 있어요</h3><p>내 일정에서 저장한 여행을 게시해 보세요.</p><small>게시·하트는 이 브라우저에서만 체험하는 모의 기능입니다.</small></div>
  return <div className="cards">{rankCommunity(posts).map((post,index)=><article className="trip-card community-card" key={post.id}>
    <button className="community-open" onClick={()=>onOpen(post)} aria-label={`${post.city} 게시 일정 보기`}>
      <div className="card-photo"><img src={`https://images.unsplash.com/${post.image}?auto=format&fit=crop&w=700&q=85`} alt={`${post.city} 여행 풍경`}/><span className="example-badge">인기 {index+1}</span><span className="photo-caption">여행자가 게시한 일정</span></div>
      <div className="card-body"><span className="country">{post.country}<span className="duration">{post.days-1}박 {post.days}일</span></span><h3>{post.city}</h3><p>{post.theme}</p></div>
    </button>
    <div className="community-meta"><span>{post.owner} 여행자 · {new Date(post.publishedAt).toLocaleDateString('ko-KR')}</span><button className={'heart-button'+(post.likedBy.includes(account)?' liked':'')} aria-label={`${post.city} 하트 ${post.likedBy.includes(account)?'취소':'보내기'} · ${post.likedBy.length}개`} aria-pressed={post.likedBy.includes(account)} onClick={()=>onHeart(post.id)}><Heart filled={post.likedBy.includes(account)}/>{post.likedBy.length}</button></div>
  </article>)}</div>
}
