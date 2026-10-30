"""A user's stars and likes: songs and albums. Liked songs are the existing favorites (me.py)."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Album, AlbumFavorite, AlbumRating, Track, TrackRating, User
from ..security import api_error, current_user
from .library import album_list_query, album_out

router = APIRouter()


class RatingIn(BaseModel):
    rating: int = Field(ge=1, le=5)


def _upsert(db: Session, model, key: dict, rating: int) -> None:
    db.execute(
        insert(model)
        .values(**key, rating=rating)
        .on_conflict_do_update(index_elements=list(key), set_={"rating": rating, "updated_at": func.now()})
    )
    db.commit()


@router.put("/ratings/tracks/{track_id}", status_code=204)
def rate_track(track_id: int, body: RatingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Track, track_id) is None:
        raise api_error(404, "not_found")
    _upsert(db, TrackRating, {"user_id": user.id, "track_id": track_id}, body.rating)


@router.delete("/ratings/tracks/{track_id}", status_code=204)
def unrate_track(track_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(TrackRating).where(TrackRating.user_id == user.id, TrackRating.track_id == track_id))
    db.commit()


@router.put("/ratings/albums/{album_id}", status_code=204)
def rate_album(album_id: int, body: RatingIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Album, album_id) is None:
        raise api_error(404, "not_found")
    _upsert(db, AlbumRating, {"user_id": user.id, "album_id": album_id}, body.rating)


@router.delete("/ratings/albums/{album_id}", status_code=204)
def unrate_album(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(AlbumRating).where(AlbumRating.user_id == user.id, AlbumRating.album_id == album_id))
    db.commit()


@router.get("/favorites/albums")
def liked_albums(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        album_list_query([])
        .join(AlbumFavorite, (AlbumFavorite.album_id == Album.id) & (AlbumFavorite.user_id == user.id))
        .group_by(AlbumFavorite.created_at)
        .order_by(AlbumFavorite.created_at.desc(), Album.id)
    )
    return {"items": [album_out(r) for r in rows]}


@router.put("/favorites/albums/{album_id}", status_code=204)
def like_album(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.get(Album, album_id) is None:
        raise api_error(404, "not_found")
    db.execute(insert(AlbumFavorite).values(user_id=user.id, album_id=album_id).on_conflict_do_nothing())
    db.commit()


@router.delete("/favorites/albums/{album_id}", status_code=204)
def unlike_album(album_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.execute(delete(AlbumFavorite).where(AlbumFavorite.user_id == user.id, AlbumFavorite.album_id == album_id))
    db.commit()

