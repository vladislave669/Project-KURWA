from datetime import datetime
from app import db, login_manager, cache
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from slugify import slugify
import jwt
from time import time
from flask import current_app
from sqlalchemy import Index, event
import os

# Cache invalidation on model changes
@event.listens_for(Movie, 'after_update')
@event.listens_for(Movie, 'after_delete')
def invalidate_movie_cache(mapper, connection, target):
    cache.delete_memoized(get_daily_views_data)
    cache.delete_memoized(calculate_storage_usage)

@event.listens_for(Category, 'after_update')
@event.listens_for(Category, 'after_delete')
def invalidate_category_cache(mapper, connection, target):
    cache.delete_memoized(get_categories_data)

@event.listens_for(MovieView, 'after_insert')
def invalidate_views_cache(mapper, connection, target):
    cache.delete_memoized(get_daily_views_data)

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, index=True)
    email = db.Column(db.String(120), unique=True, index=True)
    password_hash = db.Column(db.String(128))
    is_admin = db.Column(db.Boolean, default=False)
    reviews = db.relationship('Review', backref='author', lazy='dynamic')
    ratings = db.relationship('Rating', backref='user', lazy='dynamic')
    movie_views = db.relationship('MovieView', backref='user', lazy='dynamic')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'], algorithm='HS256')
    
    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                          algorithms=['HS256'])['reset_password']
        except:
            return None
        return User.query.get(id)

class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    slug = db.Column(db.String(200), unique=True)
    description = db.Column(db.Text)
    release_date = db.Column(db.DateTime)
    duration = db.Column(db.Integer)  # in minutes
    poster_url = db.Column(db.String(200))
    trailer_url = db.Column(db.String(200))
    category_id = db.Column(db.Integer, db.ForeignKey('category.id'))
    is_featured = db.Column(db.Boolean, default=False)
    views = db.relationship('MovieView', backref=db.backref('movie', lazy='dynamic'))
    reviews = db.relationship('Review', backref='movie', lazy='dynamic')
    ratings = db.relationship('Rating', backref='movie', lazy='dynamic')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __init__(self, *args, **kwargs):
        super(Movie, self).__init__(*args, **kwargs)
        if self.title:
            self.slug = slugify(self.title)
    
    @property
    def average_rating(self):
        ratings = [r.value for r in self.ratings.all()]
        return sum(ratings) / len(ratings) if ratings else 0
    
    @property
    def view_count(self):
        return self.views.count()
    
    @property
    def today_views(self):
        return self.views.filter(MovieView.viewed_at >= datetime.today()).count()

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True)
    slug = db.Column(db.String(64), unique=True)
    description = db.Column(db.Text)
    movies = db.relationship('Movie', backref='category', lazy='dynamic')
    
    def __init__(self, *args, **kwargs):
        super(Category, self).__init__(*args, **kwargs)
        if self.name:
            self.slug = slugify(self.name)

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.Integer, nullable=False)  # 1-5 stars
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        db.UniqueConstraint('user_id', 'movie_id', name='unique_user_movie_rating'),
    )

class MovieView(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    movie_id = db.Column(db.Integer, db.ForeignKey('movie.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Nullable for anonymous views
    ip_address = db.Column(db.String(45))  # Support IPv6
    viewed_at = db.Column(db.DateTime, default=datetime.utcnow)

# Cache functions
@cache.memoize(timeout=300)
def get_daily_views_data():
    """Get movie view statistics for the last 7 days"""
    from datetime import datetime, timedelta
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    views = MovieView.query.filter(MovieView.viewed_at >= seven_days_ago).all()
    return views

@cache.memoize(timeout=300)
def calculate_storage_usage():
    """Calculate total storage usage of movie files"""
    movies = Movie.query.all()
    total_size = 0
    for movie in movies:
        if movie.poster_url and movie.poster_url.startswith('/'):
            try:
                total_size += os.path.getsize(movie.poster_url[1:])
            except OSError:
                pass
    return total_size

@cache.memoize(timeout=300)
def get_categories_data():
    """Get all categories with their movie counts"""
    categories = Category.query.all()
    return [(cat, cat.movies.count()) for cat in categories]

# Add indexes for frequently queried columns
Index('idx_movie_created_at', Movie.created_at)
Index('idx_movie_category', Movie.category_id)
Index('idx_review_movie', Review.movie_id)
Index('idx_review_user', Review.user_id)
Index('idx_rating_movie', Rating.movie_id)
Index('idx_rating_user', Rating.user_id)
Index('idx_movieview_movie', MovieView.movie_id)
Index('idx_movieview_user', MovieView.user_id)
Index('idx_movieview_date', MovieView.viewed_at)