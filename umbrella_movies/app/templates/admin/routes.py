from flask import Blueprint, render_template, jsonify, request, current_app
from flask_login import login_required, current_user
from app.models import Movie, User, Review, Category, MovieView, Rating
from app import db, cache, limiter, csrf
from datetime import datetime, timedelta
from functools import wraps
import os
from werkzeug.utils import secure_filename
from werkzeug.exceptions import RequestEntityTooLarge

bp = Blueprint('admin', __name__, url_prefix='/admin')

# Rate limiting decorator
@limiter.limit("60/minute")
def rate_limit_admin():
    pass

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            return jsonify({'error': 'Admin privileges required'}), 403
        rate_limit_admin()
        return f(*args, **kwargs)
    return decorated_function

# Cache storage calculation
@cache.memoize(timeout=300)  # Cache for 5 minutes
def calculate_storage_usage():
    try:
        total_size = 0
        upload_folder = current_app.config['UPLOAD_FOLDER']
        for dirpath, dirnames, filenames in os.walk(upload_folder):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
        return total_size
    except Exception as e:
        current_app.logger.error(f"Error calculating storage: {str(e)}")
        return 0

# Cache daily views data
@cache.memoize(timeout=300)
def get_daily_views_data():
    try:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=6)
        dates = []
        data = []
        
        current_date = start_date
        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            dates.append(date_str)
            
            day_start = current_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = current_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            view_count = MovieView.query.filter(
                MovieView.viewed_at.between(day_start, day_end)
            ).count()
            
            data.append(view_count)
            current_date += timedelta(days=1)
        
        return {
            'labels': dates,
            'data': data
        }
    except Exception as e:
        current_app.logger.error(f"Error getting daily views: {str(e)}")
        return {'labels': [], 'data': []}

# Cache categories data
@cache.memoize(timeout=300)
def get_categories_data():
    try:
        categories = Category.query.all()
        return {
            'labels': [cat.name for cat in categories],
            'data': [cat.movies.count() for cat in categories]
        }
    except Exception as e:
        current_app.logger.error(f"Error getting categories data: {str(e)}")
        return {'labels': [], 'data': []}

@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    try:
        stats = {
            'total_movies': Movie.query.count(),
            'new_movies_today': Movie.query.filter(Movie.created_at >= datetime.today()).count(),
            'total_users': User.query.count(),
            'new_users_today': User.query.filter(User.created_at >= datetime.today()).count(),
            'total_reviews': Review.query.count(),
            'pending_reviews': Review.query.filter_by(status='pending').count(),
            'storage_used': calculate_storage_usage(),
            'storage_percentage': min(calculate_storage_usage() / (5 * 1024 * 1024 * 1024) * 100, 100)  # 5GB limit
        }
        
        chart_data = {
            'views': get_daily_views_data(),
            'categories': get_categories_data()
        }
        
        recent_movies = Movie.query.order_by(Movie.created_at.desc()).limit(5).all()
        
        return render_template('admin/dashboard.html', 
                             stats=stats,
                             chart_data=chart_data,
                             recent_movies=recent_movies)
    except Exception as e:
        current_app.logger.error(f"Error rendering dashboard: {str(e)}")
        return jsonify({'error': 'Failed to render dashboard'}), 500

@bp.route('/api/stats')
@login_required
@admin_required
def get_stats():
    try:
        stats = {
            'total_movies': Movie.query.count(),
            'new_movies_today': Movie.query.filter(Movie.created_at >= datetime.today()).count(),
            'total_users': User.query.count(),
            'new_users_today': User.query.filter(User.created_at >= datetime.today()).count(),
            'total_reviews': Review.query.count(),
            'pending_reviews': Review.query.filter_by(status='pending').count(),
            'storage_used': calculate_storage_usage(),
            'storage_percentage': min(calculate_storage_usage() / (5 * 1024 * 1024 * 1024) * 100, 100),
            'chart_data': {
                'views': get_daily_views_data(),
                'categories': get_categories_data()
            }
        }
        return jsonify(stats)
    except Exception as e:
        current_app.logger.error(f"Error getting stats: {str(e)}")
        return jsonify({'error': 'Failed to get stats'}), 500

@bp.route('/api/movies/<int:movie_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_movie(movie_id):
    try:
        movie = Movie.query.get_or_404(movie_id)
        
        # Delete associated files
        if movie.poster_url:
            poster_path = os.path.join(current_app.config['UPLOAD_FOLDER'], movie.poster_url)
            if os.path.exists(poster_path):
                os.remove(poster_path)
        
        # Delete associated reviews and ratings
        Review.query.filter_by(movie_id=movie.id).delete()
        Rating.query.filter_by(movie_id=movie.id).delete()
        MovieView.query.filter_by(movie_id=movie.id).delete()
        
        db.session.delete(movie)
        db.session.commit()
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error deleting movie: {str(e)}")
        return jsonify({'error': 'Failed to delete movie'}), 500

@bp.route('/movies/<int:movie_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_movie(movie_id):
    movie = Movie.query.get_or_404(movie_id)
    if request.method == 'POST':
        try:
            form_data = request.form
            movie.title = form_data.get('title')
            movie.description = form_data.get('description')
            movie.release_date = datetime.strptime(form_data.get('release_date'), '%Y-%m-%d')
            movie.duration = int(form_data.get('duration'))
            movie.category_id = int(form_data.get('category'))
            
            # Handle poster upload
            if 'poster' in request.files:
                file = request.files['poster']
                if file and allowed_file(file.filename):
                    # Delete old poster if exists
                    if movie.poster_url:
                        old_poster = os.path.join(current_app.config['UPLOAD_FOLDER'], movie.poster_url)
                        if os.path.exists(old_poster):
                            os.remove(old_poster)
                    
                    # Save new poster
                    filename = secure_filename(file.filename)
                    file.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
                    movie.poster_url = filename
            
            db.session.commit()
            return jsonify({'success': True})
        except RequestEntityTooLarge:
            return jsonify({'error': 'File size exceeded'}), 413
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error editing movie: {str(e)}")
            return jsonify({'error': 'Failed to edit movie'}), 500
    
    categories = Category.query.all()
    return render_template('admin/movie_form.html', movie=movie, categories=categories)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ['jpg', 'jpeg', 'png', 'gif']

@bp.route('/categories', methods=['GET'])
@login_required
@admin_required
def list_categories():
    try:
        categories = Category.query.all()
        return render_template('admin/categories.html', categories=categories)
    except Exception as e:
        current_app.logger.error(f"Error listing categories: {str(e)}")
        return jsonify({'error': 'Failed to list categories'}), 500

@bp.route('/api/categories', methods=['POST'])
@login_required
@admin_required
def create_category():
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400
            
        # Check for duplicate category
        if Category.query.filter_by(name=data['name']).first():
            return jsonify({'error': 'Category already exists'}), 400
            
        category = Category(
            name=data['name'],
            description=data.get('description', '')
        )
        db.session.add(category)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'category': {
                'id': category.id,
                'name': category.name,
                'description': category.description,
                'movie_count': category.movies.count()
            }
        })
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error creating category: {str(e)}")
        return jsonify({'error': 'Failed to create category'}), 500

@bp.route('/api/categories/<int:category_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def manage_category(category_id):
    category = Category.query.get_or_404(category_id)
    
    if request.method == 'DELETE':
        try:
            # Check if category has movies
            if category.movies.count() > 0:
                return jsonify({'error': 'Cannot delete category with associated movies'}), 400
                
            db.session.delete(category)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting category: {str(e)}")
            return jsonify({'error': 'Failed to delete category'}), 500
            
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            if 'name' in data:
                # Check for duplicate name
                existing = Category.query.filter_by(name=data['name']).first()
                if existing and existing.id != category_id:
                    return jsonify({'error': 'Category name already exists'}), 400
                category.name = data['name']
                
            if 'description' in data:
                category.description = data['description']
                
            db.session.commit()
            return jsonify({
                'success': True,
                'category': {
                    'id': category.id,
                    'name': category.name,
                    'description': category.description,
                    'movie_count': category.movies.count()
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating category: {str(e)}")
            return jsonify({'error': 'Failed to update category'}), 500

@bp.route('/users', methods=['GET'])
@login_required
@admin_required
def list_users():
    try:
        page = request.args.get('page', 1, type=int)
        per_page = 20
        users = User.query.paginate(page=page, per_page=per_page, error_out=False)
        return render_template('admin/users.html', users=users)
    except Exception as e:
        current_app.logger.error(f"Error listing users: {str(e)}")
        return jsonify({'error': 'Failed to list users'}), 500

@bp.route('/api/users/<int:user_id>', methods=['PUT', 'DELETE'])
@login_required
@admin_required
def manage_user(user_id):
    if user_id == current_user.id:
        return jsonify({'error': 'Cannot modify your own account'}), 400
        
    user = User.query.get_or_404(user_id)
    
    if request.method == 'DELETE':
        try:
            # Delete user's reviews and ratings
            Review.query.filter_by(user_id=user.id).delete()
            Rating.query.filter_by(user_id=user.id).delete()
            MovieView.query.filter_by(user_id=user.id).delete()
            
            db.session.delete(user)
            db.session.commit()
            return jsonify({'success': True})
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error deleting user: {str(e)}")
            return jsonify({'error': 'Failed to delete user'}), 500
            
    elif request.method == 'PUT':
        try:
            data = request.get_json()
            if not data:
                return jsonify({'error': 'No data provided'}), 400
                
            # Update user status (active/inactive)
            if 'is_active' in data:
                user.is_active = bool(data['is_active'])
                
            # Update admin status
            if 'is_admin' in data:
                user.is_admin = bool(data['is_admin'])
                
            db.session.commit()
            return jsonify({
                'success': True,
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'is_active': user.is_active,
                    'is_admin': user.is_admin,
                    'reviews_count': Review.query.filter_by(user_id=user.id).count(),
                    'ratings_count': Rating.query.filter_by(user_id=user.id).count()
                }
            })
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"Error updating user: {str(e)}")
            return jsonify({'error': 'Failed to update user'}), 500

@bp.route('/api/users/bulk', methods=['POST'])
@login_required
@admin_required
def bulk_user_action():
    try:
        data = request.get_json()
        if not data or 'user_ids' not in data or 'action' not in data:
            return jsonify({'error': 'User IDs and action are required'}), 400
            
        user_ids = data['user_ids']
        action = data['action']
        
        # Prevent modifying own account
        if current_user.id in user_ids:
            return jsonify({'error': 'Cannot modify your own account'}), 400
        
        users = User.query.filter(User.id.in_(user_ids)).all()
        
        if action == 'activate':
            for user in users:
                user.is_active = True
        elif action == 'deactivate':
            for user in users:
                user.is_active = False
        elif action == 'delete':
            for user in users:
                Review.query.filter_by(user_id=user.id).delete()
                Rating.query.filter_by(user_id=user.id).delete()
                MovieView.query.filter_by(user_id=user.id).delete()
                db.session.delete(user)
        else:
            return jsonify({'error': 'Invalid action'}), 400
            
        db.session.commit()
        return jsonify({'success': True, 'affected_users': len(users)})
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Error performing bulk user action: {str(e)}")
        return jsonify({'error': 'Failed to perform bulk user action'}), 500