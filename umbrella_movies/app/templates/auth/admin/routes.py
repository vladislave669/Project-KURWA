from flask import render_template, request, jsonify, current_app, flash, redirect, url_for
from flask_login import login_required, current_user
from umbrella_movies.app.admin import bp
from umbrella_movies.app.models import Movie, Category, Review, Rating, MovieView, User, UserActivity, LoginAttempt, Permission, db, BlacklistedIP, SecurityAudit, SiteCustomization, Actor
from umbrella_movies.app.decorators import admin_required, moderator_required
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from sqlalchemy import desc, func
import os
import uuid
import time
import shutil
import re
import csv
from io import StringIO
from flask import Response
import json
from umbrella_movies.app.security.monitoring import security_monitor, content_monitor, api_monitor
from umbrella_movies.app.security.ml_monitoring import ml_monitor
from umbrella_movies.app.security.advanced_ml import advanced_ml
from umbrella_movies.app.security.specialized_ml import specialized_ml
from umbrella_movies.app.security.enhanced_security import (
    enhanced_models, enhanced_features, enhanced_explainer,
    enhanced_optimizer, enhanced_response, enhanced_monitoring,
    admin_security_monitor
)
import numpy as np
from umbrella_movies.app.security.admin_protection import (
    verify_admin_session,
    check_admin_privileges,
    log_admin_action,
    detect_privilege_escalation,
    monitor_admin_behavior
)
import psutil

from .download_manager import download_manager
from .download_analytics import download_analytics
from .download_scheduler import download_scheduler
from .upload_handler import save_uploaded_file, delete_uploaded_file, get_file_url

@bp.route('/downloads/start', methods=['POST'])
@login_required
@admin_required
def start_download():
    """Start a new movie download"""
    try:
        data = request.get_json()
        movie_id = data.get('movie_id')
        url = data.get('url')
        title = data.get('title')

        if not all([movie_id, url, title]):
            return jsonify({'error': 'Missing required parameters'}), 400

        task_id = download_manager.add_download_task(movie_id, url, title)
        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': f'Download started for {title}'
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/status/<task_id>', methods=['GET'])
@login_required
@admin_required
def get_download_status(task_id):
    """Get status of a specific download task"""
    status = download_manager.get_download_status(task_id)
    if status:
        return jsonify(status)
    return jsonify({'error': 'Download task not found'}), 404

@bp.route('/downloads/all', methods=['GET'])
@login_required
@admin_required
def get_all_downloads():
    """Get status of all downloads"""
    return jsonify(download_manager.get_all_downloads())

@bp.route('/downloads/cancel/<task_id>', methods=['POST'])
@login_required
@admin_required
def cancel_download(task_id):
    """Cancel a download task"""
    if download_manager.cancel_download(task_id):
        return jsonify({'status': 'success', 'message': 'Download cancelled'})
    return jsonify({'error': 'Download task not found'}), 404

@bp.route('/downloads/retry/<task_id>', methods=['POST'])
@login_required
@admin_required
def retry_download(task_id):
    """Retry a failed download"""
    try:
        task = DownloadTask.query.get_or_404(task_id)
        if task.status != 'failed':
            return jsonify({'error': 'Only failed downloads can be retried'}), 400

        movie = Movie.query.get_or_404(task.movie_id)
        new_task_id = download_manager.add_download_task(
            movie.id,
            movie.download_url,
            movie.title
        )
        
        return jsonify({
            'status': 'success',
            'new_task_id': new_task_id,
            'message': 'Download queued for retry'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/dashboard')
@login_required
@admin_required
def download_dashboard():
    """Render download management dashboard"""
    return render_template('admin/download_dashboard.html')

@bp.route('/downloads/batch', methods=['POST'])
@login_required
@admin_required
def start_batch_download():
    """Start batch download of movies"""
    try:
        data = request.get_json()
        movies = data.get('movies', [])
        
        if not movies:
            return jsonify({'error': 'No movies provided'}), 400
        
        task_ids = download_manager.add_batch_download(movies)
        return jsonify({
            'status': 'success',
            'task_ids': task_ids,
            'message': f'Started {len(task_ids)} downloads'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/pause-all', methods=['POST'])
@login_required
@admin_required
def pause_all_downloads():
    """Pause all active downloads"""
    if download_manager.pause_all_downloads():
        return jsonify({'status': 'success', 'message': 'All downloads paused'})
    return jsonify({'error': 'Failed to pause downloads'}), 500

@bp.route('/downloads/resume-all', methods=['POST'])
@login_required
@admin_required
def resume_all_downloads():
    """Resume all paused downloads"""
    if download_manager.resume_all_downloads():
        return jsonify({'status': 'success', 'message': 'All downloads resumed'})
    return jsonify({'error': 'Failed to resume downloads'}), 500

@bp.route('/downloads/clear-completed', methods=['POST'])
@login_required
@admin_required
def clear_completed_downloads():
    """Clear completed downloads history"""
    count = download_manager.clear_completed_downloads()
    return jsonify({
        'status': 'success',
        'message': f'Cleared {count} completed downloads'
    })

@bp.route('/downloads/priority/<task_id>', methods=['POST'])
@login_required
@admin_required
def set_download_priority(task_id):
    """Set priority for a download task"""
    try:
        data = request.get_json()
        priority = data.get('priority')
        
        if priority is None:
            return jsonify({'error': 'Priority not provided'}), 400
        
        if download_manager.set_priority(task_id, priority):
            return jsonify({'status': 'success', 'message': 'Priority updated'})
        return jsonify({'error': 'Download task not found'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/analytics/stats')
@login_required
@admin_required
def get_download_stats():
    """Get download statistics"""
    period = request.args.get('period', 'day')
    return jsonify(download_analytics.get_download_stats(period))

@bp.route('/downloads/analytics/trends')
@login_required
@admin_required
def get_download_trends():
    """Get download trends"""
    period = request.args.get('period', 'day')
    return jsonify(download_analytics.get_download_trends(period))

@bp.route('/downloads/analytics/errors')
@login_required
@admin_required
def get_error_analysis():
    """Get download error analysis"""
    period = request.args.get('period', 'day')
    return jsonify(download_analytics.get_error_analysis(period))

@bp.route('/downloads/analytics/popular')
@login_required
@admin_required
def get_popular_downloads():
    """Get most popular downloads"""
    limit = request.args.get('limit', 10, type=int)
    return jsonify(download_analytics.get_popular_downloads(limit))

@bp.route('/downloads/analytics/speed')
@login_required
@admin_required
def get_speed_analysis():
    """Get download speed analysis"""
    period = request.args.get('period', 'day')
    return jsonify(download_analytics.get_download_speed_analysis(period))

@bp.route('/system/health')
@login_required
@admin_required
def get_system_health():
    """Get system health metrics"""
    try:
        # Get disk usage
        movies_dir = Path(current_app.config['MOVIES_DIRECTORY'])
        disk_usage = psutil.disk_usage(str(movies_dir))
        disk_percent = disk_usage.percent

        # Get memory usage
        memory = psutil.virtual_memory()
        memory_percent = memory.percent

        # Get network usage (simplified)
        net_io = psutil.net_io_counters()
        net_percent = min((net_io.bytes_sent + net_io.bytes_recv) / 1e8, 100)  # Simplified calculation

        return jsonify({
            'disk_usage': disk_percent,
            'memory_usage': memory_percent,
            'network_usage': net_percent,
            'disk_free': disk_usage.free / (1024 * 1024 * 1024),  # GB
            'memory_free': memory.available / (1024 * 1024 * 1024),  # GB
            'timestamp': datetime.utcnow().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/available')
@login_required
@admin_required
def get_available_movies():
    """Get list of movies available for download"""
    try:
        movies = Movie.query.filter(
            Movie.download_url.isnot(None),
            ~Movie.id.in_(
                db.session.query(DownloadTask.movie_id).filter(
                    DownloadTask.status.in_(['downloading', 'queued', 'completed'])
                )
            )
        ).all()
        
        return jsonify([{
            'id': movie.id,
            'title': movie.title,
            'size': movie.file_size,
            'url': movie.download_url
        } for movie in movies])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/cleanup', methods=['POST'])
@login_required
@admin_required
def cleanup_downloads():
    """Clean up incomplete and failed downloads"""
    try:
        # Get all incomplete downloads
        incomplete_tasks = DownloadTask.query.filter(
            DownloadTask.status.in_(['failed', 'cancelled'])
        ).all()

        cleaned_count = 0
        for task in incomplete_tasks:
            try:
                # Remove partial download file if exists
                file_path = Path(current_app.config['MOVIES_DIRECTORY']) / f"{task.movie_id}.part"
                if file_path.exists():
                    file_path.unlink()
                cleaned_count += 1
            except Exception as e:
                logging.error(f"Error cleaning up task {task.id}: {str(e)}")

        return jsonify({
            'status': 'success',
            'cleaned_count': cleaned_count,
            'message': f'Cleaned up {cleaned_count} incomplete downloads'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/optimize', methods=['POST'])
@login_required
@admin_required
def optimize_downloads():
    """Optimize download queue and settings"""
    try:
        # Get system resources
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(str(Path(current_app.config['MOVIES_DIRECTORY'])))
        
        # Adjust concurrent downloads based on resources
        max_concurrent = 3  # Default
        if memory.percent < 50 and disk.percent < 70:
            max_concurrent = 5
        elif memory.percent > 80 or disk.percent > 90:
            max_concurrent = 2

        # Update download manager settings
        download_manager.max_concurrent_downloads = max_concurrent
        download_manager.optimize_queue()

        return jsonify({
            'status': 'success',
            'max_concurrent': max_concurrent,
            'message': 'Download settings optimized'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/schedule', methods=['POST'])
@login_required
@admin_required
def schedule_download():
    """Schedule a new download"""
    try:
        data = request.get_json()
        movie_id = data.get('movie_id')
        scheduled_time = datetime.fromisoformat(data.get('scheduled_time'))
        priority = data.get('priority', 2)
        bandwidth_limit = data.get('bandwidth_limit')

        task_id = download_scheduler.schedule_download(
            movie_id, scheduled_time, priority, bandwidth_limit
        )

        return jsonify({
            'status': 'success',
            'task_id': task_id,
            'message': 'Download scheduled successfully'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/schedule/batch', methods=['POST'])
@login_required
@admin_required
def schedule_batch_downloads():
    """Schedule multiple downloads with optimal timing"""
    try:
        data = request.get_json()
        downloads = data.get('downloads', [])
        
        # Get optimal schedule
        schedule = download_scheduler.get_optimal_schedule(downloads)
        
        # Schedule all downloads
        task_ids = []
        for download in schedule:
            task_id = download_scheduler.schedule_download(
                download['movie_id'],
                download['scheduled_time'],
                download.get('priority', 2)
            )
            task_ids.append(task_id)
        
        return jsonify({
            'status': 'success',
            'task_ids': task_ids,
            'message': f'Scheduled {len(task_ids)} downloads'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/schedule/<task_id>', methods=['DELETE'])
@login_required
@admin_required
def cancel_scheduled_download(task_id):
    """Cancel a scheduled download"""
    if download_scheduler.cancel_scheduled_download(task_id):
        return jsonify({
            'status': 'success',
            'message': 'Scheduled download cancelled'
        })
    return jsonify({'error': 'Download not found or already started'}), 404

@bp.route('/downloads/schedule/<task_id>', methods=['PUT'])
@login_required
@admin_required
def reschedule_download(task_id):
    """Reschedule a download"""
    try:
        data = request.get_json()
        new_time = datetime.fromisoformat(data.get('scheduled_time'))
        
        if download_scheduler.reschedule_download(task_id, new_time):
            return jsonify({
                'status': 'success',
                'message': 'Download rescheduled successfully'
            })
        return jsonify({'error': 'Download not found or already started'}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/downloads/schedule', methods=['GET'])
@login_required
@admin_required
def get_scheduled_downloads():
    """Get all scheduled downloads"""
    downloads = download_scheduler.get_scheduled_downloads()
    return jsonify(downloads)

@bp.route('/downloads/schedule/optimize', methods=['POST'])
@login_required
@admin_required
def optimize_schedule():
    """Optimize current download schedule"""
    try:
        # Get all scheduled downloads
        current_schedule = download_scheduler.get_scheduled_downloads()
        
        # Convert to format expected by get_optimal_schedule
        downloads = [{
            'movie_id': Movie.query.filter_by(title=d['movie_title']).first().id,
            'priority': d['priority']
        } for d in current_schedule]
        
        # Get optimal schedule
        new_schedule = download_scheduler.get_optimal_schedule(downloads)
        
        # Reschedule all downloads
        for i, download in enumerate(new_schedule):
            download_scheduler.reschedule_download(
                current_schedule[i]['task_id'],
                download['scheduled_time']
            )
        
        return jsonify({
            'status': 'success',
            'message': f'Optimized schedule for {len(new_schedule)} downloads'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/actors', methods=['GET'])
@login_required
@admin_required
def list_actors():
    """Get all actors"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    
    actors = Actor.query.order_by(Actor.name).paginate(
        page=page, per_page=per_page, error_out=False
    )
    
    return jsonify({
        'actors': [actor.to_dict() for actor in actors.items],
        'total': actors.total,
        'pages': actors.pages,
        'current_page': actors.page
    })

@bp.route('/actors/<int:actor_id>', methods=['GET'])
@login_required
@admin_required
def get_actor(actor_id):
    """Get actor details"""
    actor = Actor.query.get_or_404(actor_id)
    return jsonify(actor.to_dict())

@bp.route('/actors', methods=['POST'])
@login_required
@admin_required
def create_actor():
    """Create a new actor"""
    try:
        data = request.get_json()
        
        # Convert birth_date string to date object
        birth_date = None
        if data.get('birth_date'):
            birth_date = datetime.fromisoformat(data['birth_date']).date()
        
        actor = Actor(
            name=data['name'],
            biography=data.get('biography'),
            birth_date=birth_date,
            nationality=data.get('nationality'),
            image_url=data.get('image_url')
        )
        
        db.session.add(actor)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Actor created successfully',
            'actor': actor.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/actors/<int:actor_id>', methods=['PUT'])
@login_required
@admin_required
def update_actor(actor_id):
    """Update actor details"""
    try:
        actor = Actor.query.get_or_404(actor_id)
        data = request.get_json()
        
        if 'name' in data:
            actor.name = data['name']
        if 'biography' in data:
            actor.biography = data['biography']
        if 'birth_date' in data:
            actor.birth_date = datetime.fromisoformat(data['birth_date']).date()
        if 'nationality' in data:
            actor.nationality = data['nationality']
        if 'image_url' in data:
            actor.image_url = data['image_url']
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Actor updated successfully',
            'actor': actor.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/actors/<int:actor_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_actor(actor_id):
    """Delete an actor"""
    try:
        actor = Actor.query.get_or_404(actor_id)
        db.session.delete(actor)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Actor deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/<int:movie_id>/actors', methods=['POST'])
@login_required
@admin_required
def add_movie_actors(movie_id):
    """Add actors to a movie"""
    try:
        movie = Movie.query.get_or_404(movie_id)
        data = request.get_json()
        actor_ids = data.get('actor_ids', [])
        
        actors = Actor.query.filter(Actor.id.in_(actor_ids)).all()
        movie.actors.extend(actors)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Actors added to movie successfully',
            'movie': movie.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/<int:movie_id>/actors/<int:actor_id>', methods=['DELETE'])
@login_required
@admin_required
def remove_movie_actor(movie_id, actor_id):
    """Remove an actor from a movie"""
    try:
        movie = Movie.query.get_or_404(movie_id)
        actor = Actor.query.get_or_404(actor_id)
        
        if actor in movie.actors:
            movie.actors.remove(actor)
            db.session.commit()
            
        return jsonify({
            'status': 'success',
            'message': 'Actor removed from movie successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/edit/<int:movie_id>', methods=['GET'])
@login_required
@admin_required
def edit_movie(movie_id):
    """Edit movie page"""
    movie = Movie.query.get_or_404(movie_id)
    actors = Actor.query.order_by(Actor.name).all()
    return render_template('admin/movie_edit.html', movie=movie, actors=actors)

@bp.route('/movies/<int:movie_id>', methods=['PUT'])
@login_required
@admin_required
def update_movie(movie_id):
    """Update movie details"""
    try:
        movie = Movie.query.get_or_404(movie_id)
        data = request.get_json()
        
        # Update basic movie details
        movie.title = data.get('title', movie.title)
        movie.description = data.get('description')
        if data.get('release_date'):
            movie.release_date = datetime.fromisoformat(data['release_date']).date()
        movie.duration = data.get('duration')
        movie.genre = data.get('genre')
        movie.thumbnail_url = data.get('thumbnail_url')
        movie.download_url = data.get('download_url')
        
        # Update actors
        if 'actor_ids' in data:
            actors = Actor.query.filter(Actor.id.in_(data['actor_ids'])).all()
            movie.actors = actors
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Movie updated successfully',
            'movie': movie.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/view/<int:movie_id>', methods=['GET'])
@login_required
@admin_required
def view_movie(movie_id):
    """View movie details page"""
    movie = Movie.query.get_or_404(movie_id)
    return render_template('admin/movie_view.html', movie=movie)

@bp.route('/upload/image', methods=['POST'])
@login_required
@admin_required
def upload_image():
    """Handle image upload for actors and movies"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file provided'}), 400
        
        file = request.files['file']
        upload_type = request.form.get('type', 'movie')
        
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        result = save_uploaded_file(file, upload_type)
        if result:
            return jsonify({
                'status': 'success',
                'message': 'File uploaded successfully',
                'file_info': result
            })
        
        return jsonify({'error': 'Invalid file type'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/<int:movie_id>/cast', methods=['POST'])
@login_required
@admin_required
def update_movie_cast(movie_id):
    """Update movie cast with role information"""
    try:
        movie = Movie.query.get_or_404(movie_id)
        data = request.get_json()
        cast_data = data.get('cast', [])
        
        # Clear existing roles
        MovieActor.query.filter_by(movie_id=movie_id).delete()
        
        # Add new roles
        for role in cast_data:
            actor_id = role.get('actor_id')
            if actor_id:
                movie_actor = MovieActor(
                    movie_id=movie_id,
                    actor_id=actor_id,
                    character_name=role.get('character_name'),
                    role_description=role.get('role_description'),
                    is_main_character=role.get('is_main_character', False)
                )
                db.session.add(movie_actor)
        
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Cast updated successfully',
            'cast': movie.get_cast_details()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/actors/<int:actor_id>/stats', methods=['GET'])
@login_required
@admin_required
def get_actor_stats(actor_id):
    """Get actor's filmography statistics"""
    try:
        actor = Actor.query.get_or_404(actor_id)
        stats = actor.get_filmography_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/<int:movie_id>/reviews', methods=['GET'])
@login_required
@admin_required
def get_movie_reviews(movie_id):
    """Get all reviews for a movie"""
    try:
        page = request.args.get('page', 1, type=int)
        per_page = request.args.get('per_page', 10, type=int)
        
        reviews = Review.query.filter_by(movie_id=movie_id)\
            .order_by(Review.created_at.desc())\
            .paginate(page=page, per_page=per_page, error_out=False)
        
        return jsonify({
            'reviews': [review.to_dict() for review in reviews.items],
            'total': reviews.total,
            'pages': reviews.pages,
            'current_page': reviews.page
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@bp.route('/movies/<int:movie_id>/reviews/<int:review_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_review(movie_id, review_id):
    """Delete a movie review"""
    try:
        review = Review.query.get_or_404(review_id)
        if review.movie_id != movie_id:
            return jsonify({'error': 'Review does not belong to this movie'}), 400
        
        db.session.delete(review)
        db.session.commit()
        
        return jsonify({
            'status': 'success',
            'message': 'Review deleted successfully'
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def admin_required(f):
    """Enhanced admin decorator with security checks"""
    @login_required
    def decorated_function(*args, **kwargs):
        start_time = datetime.utcnow()
        
        # Extract enhanced features
        features = enhanced_features.extract_enhanced_features(
            request,
            current_user.id if current_user.is_authenticated else None,
            admin_context=True
        )
        
        # Verify admin session
        if not verify_admin_session(current_user, features):
            enhanced_monitoring.track_threat('unauthorized_admin_access', 'critical')
            enhanced_response.execute_response('unauthorized_admin_access', 'critical', {
                'user_id': current_user.id,
                'features': features
            })
            abort(403)
            
        # Check admin privileges
        if not check_admin_privileges(current_user, request.endpoint):
            enhanced_monitoring.track_threat('privilege_escalation', 'critical')
            enhanced_response.execute_response('privilege_escalation', 'critical', {
                'user_id': current_user.id,
                'endpoint': request.endpoint,
                'features': features
            })
            abort(403)
            
        # Monitor admin behavior
        behavior_score = monitor_admin_behavior(current_user, request, features)
        if behavior_score > 0.7:
            enhanced_monitoring.track_threat('suspicious_admin_behavior', 'high')
            enhanced_response.execute_response('suspicious_admin_behavior', 'high', {
                'user_id': current_user.id,
                'behavior_score': behavior_score,
                'features': features
            })
            
        # Track admin action
        log_admin_action(current_user, request, features)
        
        # Track metrics
        enhanced_monitoring.track_request(
            request,
            (datetime.utcnow() - start_time).total_seconds(),
            admin_context=True
        )
        
        return f(*args, **kwargs)
    return decorated_function

@bp.before_request
def before_request():
    """Security checks before processing any admin request"""
    if not current_user.is_authenticated:
        return
        
    start_time = datetime.utcnow()
    
    # Extract enhanced features
    features = enhanced_features.extract_enhanced_features(
        request,
        current_user.id,
        admin_context=True
    )
    
    # Check for privilege escalation attempts
    if detect_privilege_escalation(current_user, request, features):
        enhanced_monitoring.track_threat('privilege_escalation_attempt', 'critical')
        enhanced_response.execute_response('privilege_escalation_attempt', 'critical', {
            'user_id': current_user.id,
            'features': features
        })
        abort(403)
        
    # Advanced threat detection for admin panel
    admin_threats = enhanced_models.admin_threat_model.predict_proba(
        [list(features['admin_features'].values())]
    )[0]
    
    if any(score > 0.7 for score in admin_threats):
        threat_type = ['session_hijacking', 'privilege_escalation', 'unauthorized_access'][
            np.argmax(admin_threats)
        ]
        enhanced_monitoring.track_threat(f'admin_{threat_type}', 'critical')
        enhanced_response.execute_response(f'admin_{threat_type}', 'critical', {
            'user_id': current_user.id,
            'features': features
        })
        abort(403)
        
    # Generate explanations for suspicious admin activity
    if any(score > 0.5 for score in admin_threats):
        explanation = enhanced_explainer.explain_prediction(
            enhanced_models.admin_threat_model,
            features,
            max(admin_threats)
        )
        
        admin_security_monitor.log_security_event(
            'suspicious_admin_activity',
            {
                'user_id': current_user.id,
                'features': features,
                'explanation': explanation,
                'threat_scores': dict(zip(
                    ['session_hijacking', 'privilege_escalation', 'unauthorized_access'],
                    admin_threats
                ))
            },
            severity='high'
        )
        
    # Track metrics
    enhanced_monitoring.track_request(
        request,
        (datetime.utcnow() - start_time).total_seconds(),
        admin_context=True
    )

@bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard view"""
    stats = {
        'total_users': User.query.count(),
        'total_movies': Movie.query.count(),
        'total_reviews': Review.query.count(),
        'total_views': MovieView.query.count(),
        'recent_activities': UserActivity.query.order_by(UserActivity.created_at.desc()).limit(10).all(),
        'recent_users': User.query.order_by(User.created_at.desc()).limit(5).all(),
        'popular_movies': Movie.query.join(MovieView).group_by(Movie.id).order_by(
            desc(func.count(MovieView.id))).limit(5).all(),
        'storage_percentage': check_storage_health().get('usage', 0)
    }
    return render_template('admin/dashboard.html', stats=stats)

@bp.route('/stats')
@login_required
@admin_required
def get_stats():
    """Get dashboard statistics"""
    total_movies = Movie.query.count()
    total_views = MovieView.query.count()
    total_reviews = Review.query.count()
    avg_rating = db.session.query(func.avg(Rating.value)).scalar() or 0
    
    # Get daily views for the past week
    daily_views = db.session.query(
        func.date(MovieView.viewed_at).label('date'),
        func.count(MovieView.id).label('views')
    ).group_by(func.date(MovieView.viewed_at))\
     .order_by(desc('date'))\
     .limit(7)\
     .all()
    
    chart_data = {
        'labels': [str(view.date) for view in daily_views],
        'views': [view.views for view in daily_views]
    }
    
    return jsonify({
        'total_movies': total_movies,
        'total_views': total_views,
        'total_reviews': total_reviews,
        'avg_rating': round(float(avg_rating), 1),
        'chart_data': chart_data
    })

@bp.route('/upload', methods=['POST'])
@login_required
@admin_required
def upload_movie():
    """Upload a new movie"""
    if 'poster' not in request.files:
        return jsonify({'error': 'No poster file'}), 400
    
    poster = request.files['poster']
    if poster.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if not allowed_file(poster.filename):
        return jsonify({'error': 'Invalid file type'}), 400
    
    try:
        # Save poster file
        filename = secure_filename(f"{uuid.uuid4()}_{poster.filename}")
        poster.save(os.path.join(current_app.config['UPLOAD_FOLDER'], filename))
        
        # Create movie record
        movie = Movie(
            title=request.form['title'],
            description=request.form['description'],
            release_year=int(request.form['release_year']),
            duration=int(request.form['duration']),
            category_id=int(request.form['category_id']),
            poster_path=filename,
            trailer_url=request.form['trailer_url'],
            is_featured=bool(request.form.get('is_featured', False))
        )
        
        db.session.add(movie)
        db.session.commit()
        
        SecurityAudit.log(
            'movie_added',
            user_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            details={
                'movie_id': movie.id,
                'title': movie.title
            },
            severity='medium'
        )
        
        return jsonify({
            'message': 'Movie uploaded successfully',
            'movie_id': movie.id
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/movie/<int:movie_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_movie(movie_id):
    """Delete a movie"""
    movie = Movie.query.get_or_404(movie_id)
    
    try:
        # Delete poster file
        if movie.poster_path:
            poster_path = os.path.join(current_app.config['UPLOAD_FOLDER'], movie.poster_path)
            if os.path.exists(poster_path):
                os.remove(poster_path)
        
        # Delete movie record
        db.session.delete(movie)
        db.session.commit()
        
        SecurityAudit.log(
            'movie_deleted',
            user_id=current_user.id,
            ip_address=request.remote_addr,
            user_agent=request.user_agent.string,
            details={
                'movie_id': movie_id,
                'title': movie.title
            },
            severity='high'
        )
        
        return jsonify({'message': 'Movie deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@bp.route('/activity-log')
@login_required
@admin_required
def activity_log():
    """Get recent user activities"""
    activities = db.session.query(
        UserActivity, User.username
    ).join(User).order_by(
        UserActivity.created_at.desc()
    ).limit(50).all()
    
    return jsonify({
        'activities': [{
            'username': activity.username,
            'action': activity.UserActivity.action,
            'details': activity.UserActivity.details,
            'ip_address': activity.UserActivity.ip_address,
            'created_at': activity.UserActivity.created_at.isoformat()
        } for activity in activities]
    })

@bp.route('/login-attempts')
@login_required
@admin_required
def login_attempts():
    """Get recent login attempts"""
    attempts = LoginAttempt.query.order_by(
        LoginAttempt.created_at.desc()
    ).limit(50).all()
    
    return jsonify({
        'attempts': [{
            'email': attempt.email,
            'ip_address': attempt.ip_address,
            'success': attempt.success,
            'created_at': attempt.created_at.isoformat()
        } for attempt in attempts]
    })

@bp.route('/user/<int:user_id>/lock', methods=['POST'])
@login_required
@admin_required
def lock_user(user_id):
    """Lock a user account"""
    user = User.query.get_or_404(user_id)
    if user.is_administrator():
        return jsonify({'error': 'Cannot lock administrator accounts'}), 403
        
    duration = request.json.get('duration', 30)  # Default 30 minutes
    
    user.lock_account(duration)
    user.log_activity(
        'account_locked',
        details=f'Account locked for {duration} minutes by admin',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    SecurityAudit.log(
        'user_account_locked',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={
            'target_user_id': user.id,
            'lock_duration_hours': duration,
            'unlock_time': user.locked_until.isoformat()
        },
        severity='high'
    )
    
    return jsonify({'message': f'User account locked for {duration} minutes'})

@bp.route('/user/<int:user_id>/unlock', methods=['POST'])
@login_required
@admin_required
def unlock_user(user_id):
    """Unlock a user account"""
    user = User.query.get_or_404(user_id)
    user.reset_login_attempts()
    user.log_activity(
        'account_unlocked',
        details='Account unlocked by admin',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    
    SecurityAudit.log(
        'user_account_unlocked',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={'target_user_id': user.id},
        severity='high'
    )
    
    return jsonify({'message': 'User account unlocked'})

@bp.route('/user/<int:user_id>/role', methods=['POST'])
@login_required
@admin_required
def change_user_role(user_id):
    """Change a user's role"""
    user = User.query.get_or_404(user_id)
    if user.is_administrator() and user != current_user:
        return jsonify({'error': 'Cannot modify administrator roles'}), 403
        
    role_name = request.json.get('role')
    if not role_name:
        return jsonify({'error': 'Role name is required'}), 400
        
    role = Permission.query.filter_by(name=role_name).first()
    if not role:
        return jsonify({'error': 'Invalid role'}), 400
        
    old_role = user.role.name if user.role else None
    user.role = role
    user.log_activity(
        'role_changed',
        details=f'Role changed to {role_name} by admin',
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string
    )
    db.session.commit()
    
    SecurityAudit.log(
        'user_role_updated',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={
            'target_user_id': user.id,
            'old_role': old_role,
            'new_role': user.role.name
        },
        severity='high'
    )
    
    return jsonify({'message': f'User role changed to {role_name}'})

@bp.route('/users')
@login_required
@admin_required
def list_users():
    """List all users with their roles and status"""
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    
    users = User.query.paginate(page=page, per_page=per_page)
    
    return jsonify({
        'users': [{
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'role': user.role.name,
            'active': user.active,
            'locked': user.is_locked(),
            'last_seen': user.last_seen.isoformat() if user.last_seen else None,
            'created_at': user.created_at.isoformat()
        } for user in users.items],
        'total': users.total,
        'pages': users.pages,
        'current_page': users.page
    })

@bp.route('/user/<int:user_id>/activity')
@login_required
@admin_required
def user_activity(user_id):
    """Get activity history for a specific user"""
    user = User.query.get_or_404(user_id)
    activities = UserActivity.query.filter_by(user_id=user_id).order_by(
        UserActivity.created_at.desc()
    ).limit(100).all()
    
    return jsonify({
        'activities': [{
            'action': activity.action,
            'details': activity.details,
            'ip_address': activity.ip_address,
            'created_at': activity.created_at.isoformat()
        } for activity in activities]
    })

@bp.route('/security-overview')
@login_required
@admin_required
def security_overview():
    """Get security overview data"""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    
    # Get failed login attempts in last 24 hours
    failed_logins = LoginAttempt.query.filter(
        LoginAttempt.created_at >= day_ago,
        LoginAttempt.success == False
    ).count()
    
    # Get locked accounts
    locked_accounts = User.query.filter(
        User.locked_until > now
    ).count()
    
    # Get active sessions (users seen in last 15 minutes)
    active_sessions = User.query.filter(
        User.last_seen >= now - timedelta(minutes=15)
    ).count()
    
    # Get suspicious activities
    suspicious_activities = UserActivity.query.filter(
        UserActivity.created_at >= day_ago,
        UserActivity.action.in_(['failed_login', 'password_reset', 'account_locked'])
    ).count()
    
    # Get system health
    db_health = check_database_health()
    storage_health = check_storage_health()
    cache_health = check_cache_health()
    api_health = check_api_health()
    
    # Get active security alerts
    alerts = get_security_alerts()
    
    return jsonify({
        'failed_logins': failed_logins,
        'locked_accounts': locked_accounts,
        'active_sessions': active_sessions,
        'suspicious_activities': suspicious_activities,
        'system_health': {
            'database': db_health,
            'storage': storage_health,
            'cache': cache_health,
            'api': api_health
        },
        'alerts': alerts
    })

def check_database_health():
    """Check database connection and performance"""
    try:
        # Measure query execution time
        start_time = time.time()
        db.session.execute('SELECT 1')
        response_time = (time.time() - start_time) * 1000  # Convert to milliseconds
        
        status = 100 if response_time < 100 else (
            80 if response_time < 500 else 60
        )
        
        return {
            'status': status,
            'message': 'Healthy' if status > 80 else 'Degraded',
            'response_time': round(response_time, 2)
        }
    except Exception as e:
        return {
            'status': 0,
            'message': 'Error',
            'error': str(e)
        }

def check_storage_health():
    """Check storage usage"""
    try:
        upload_dir = current_app.config['UPLOAD_FOLDER']
        total, used, free = shutil.disk_usage(upload_dir)
        usage_percent = (used / total) * 100
        
        return {
            'usage': round(usage_percent, 1),
            'total': total,
            'used': used,
            'free': free
        }
    except Exception as e:
        return {
            'usage': 0,
            'error': str(e)
        }

def check_cache_health():
    """Check cache status"""
    try:
        # Add your cache health check logic here
        # For example, if using Redis:
        # redis_client.ping()
        return {
            'status': 100,
            'message': 'Operational'
        }
    except Exception as e:
        return {
            'status': 0,
            'message': 'Error',
            'error': str(e)
        }

def check_api_health():
    """Check API response times"""
    try:
        start_time = time.time()
        # Make a sample API request
        response_time = (time.time() - start_time) * 1000
        
        status = 100 if response_time < 100 else (
            80 if response_time < 500 else 60
        )
        
        return {
            'status': status,
            'response_time': round(response_time, 2)
        }
    except Exception as e:
        return {
            'status': 0,
            'error': str(e)
        }

def get_security_alerts():
    """Get active security alerts"""
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    
    alerts = []
    
    # Check for multiple failed login attempts from same IP
    suspicious_ips = db.session.query(
        LoginAttempt.ip_address,
        func.count(LoginAttempt.id).label('attempts')
    ).filter(
        LoginAttempt.created_at >= day_ago,
        LoginAttempt.success == False
    ).group_by(
        LoginAttempt.ip_address
    ).having(
        func.count(LoginAttempt.id) >= 10
    ).all()
    
    for ip, attempts in suspicious_ips:
        alerts.append({
            'id': f'failed_login_{ip}',
            'level': 'danger',
            'title': 'Multiple Failed Login Attempts',
            'message': f'{attempts} failed login attempts from IP {ip}',
            'timestamp': now.isoformat()
        })
    
    # Check for locked accounts
    locked_count = User.query.filter(
        User.locked_until > now
    ).count()
    
    if locked_count > 0:
        alerts.append({
            'id': 'locked_accounts',
            'level': 'warning',
            'title': 'Locked User Accounts',
            'message': f'{locked_count} user accounts are currently locked',
            'timestamp': now.isoformat()
        })
    
    # Check storage usage
    storage = check_storage_health()
    if storage.get('usage', 0) > 90:
        alerts.append({
            'id': 'storage_warning',
            'level': 'warning',
            'title': 'High Storage Usage',
            'message': f'Storage usage is at {storage["usage"]}%',
            'timestamp': now.isoformat()
        })
    
    # Check database health
    db_health = check_database_health()
    if db_health['status'] < 80:
        alerts.append({
            'id': 'database_health',
            'level': 'danger',
            'title': 'Database Performance Issue',
            'message': f'Database response time: {db_health["response_time"]}ms',
            'timestamp': now.isoformat()
        })
    
    return alerts

@bp.route('/security-alert/<alert_id>/dismiss', methods=['POST'])
@login_required
@admin_required
def dismiss_alert(alert_id):
    """Dismiss a security alert"""
    # Add logic to dismiss/acknowledge alert
    return jsonify({'message': 'Alert dismissed'})

@bp.route('/security-alerts/clear', methods=['POST'])
@login_required
@admin_required
def clear_alerts():
    """Clear all security alerts"""
    # Add logic to clear all alerts
    return jsonify({'message': 'All alerts cleared'})

@bp.route('/ip-blacklist')
@login_required
@admin_required
def get_ip_blacklist():
    blacklist = BlacklistedIP.query.all()
    return jsonify({
        'blacklist': [{
            'id': ip.id,
            'ip_address': ip.ip_address,
            'reason': ip.reason,
            'added_by_name': User.query.get(ip.added_by).username if ip.added_by else 'System',
            'created_at': ip.created_at.isoformat(),
            'expires_at': ip.expires_at.isoformat() if ip.expires_at else None,
            'is_active': ip.is_active
        } for ip in blacklist]
    })

@bp.route('/ip-blacklist/add', methods=['POST'])
@login_required
@admin_required
def add_to_blacklist():
    data = request.get_json()
    
    if not data.get('ip_address'):
        return jsonify({'error': 'IP address is required'}), 400
        
    if not re.match(r'^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$', data['ip_address']):
        return jsonify({'error': 'Invalid IP address format'}), 400
        
    existing = BlacklistedIP.query.filter_by(ip_address=data['ip_address']).first()
    if existing:
        return jsonify({'error': 'IP address is already blacklisted'}), 400
        
    blacklist = BlacklistedIP(
        ip_address=data['ip_address'],
        reason=data.get('reason'),
        added_by=current_user.id,
        expires_at=datetime.fromisoformat(data['expires_at']) if data.get('expires_at') else None
    )
    
    db.session.add(blacklist)
    db.session.commit()
    
    SecurityAudit.log(
        'ip_blacklisted',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={'blacklisted_ip': data['ip_address'], 'reason': data.get('reason')},
        severity='high'
    )
    
    return jsonify({'message': 'IP added to blacklist'})

@bp.route('/ip-blacklist/<int:id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_ip(id):
    blacklist = BlacklistedIP.query.get_or_404(id)
    blacklist.is_active = False
    db.session.commit()
    
    SecurityAudit.log(
        'ip_blacklist_deactivated',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={'ip': blacklist.ip_address},
        severity='medium'
    )
    
    return jsonify({'message': 'IP deactivated'})

@bp.route('/ip-blacklist/<int:id>/activate', methods=['POST'])
@login_required
@admin_required
def activate_ip(id):
    blacklist = BlacklistedIP.query.get_or_404(id)
    blacklist.is_active = True
    db.session.commit()
    
    SecurityAudit.log(
        'ip_blacklist_activated',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={'ip': blacklist.ip_address},
        severity='medium'
    )
    
    return jsonify({'message': 'IP activated'})

@bp.route('/ip-blacklist/<int:id>', methods=['DELETE'])
@login_required
@admin_required
def delete_ip(id):
    blacklist = BlacklistedIP.query.get_or_404(id)
    ip_address = blacklist.ip_address
    db.session.delete(blacklist)
    db.session.commit()
    
    SecurityAudit.log(
        'ip_blacklist_deleted',
        user_id=current_user.id,
        ip_address=request.remote_addr,
        user_agent=request.user_agent.string,
        details={'ip': ip_address},
        severity='high'
    )
    
    return jsonify({'message': 'IP deleted from blacklist'})

@bp.route('/security-audit')
@login_required
@admin_required
def get_security_audit():
    page = request.args.get('page', 1, type=int)
    severity = request.args.get('severity')
    event_type = request.args.get('event_type')
    date = request.args.get('date')
    
    query = SecurityAudit.query
    
    if severity:
        query = query.filter_by(severity=severity)
    if event_type:
        query = query.filter_by(event_type=event_type)
    if date:
        start_date = datetime.strptime(date, '%Y-%m-%d')
        end_date = start_date + timedelta(days=1)
        query = query.filter(SecurityAudit.created_at.between(start_date, end_date))
        
    query = query.order_by(SecurityAudit.created_at.desc())
    pagination = query.paginate(page=page, per_page=20)
    
    event_types = db.session.query(SecurityAudit.event_type).distinct().all()
    
    return jsonify({
        'audits': [{
            'id': audit.id,
            'event_type': audit.event_type,
            'username': User.query.get(audit.user_id).username if audit.user_id else None,
            'ip_address': audit.ip_address,
            'user_agent': audit.user_agent,
            'details': audit.details,
            'severity': audit.severity,
            'created_at': audit.created_at.isoformat()
        } for audit in pagination.items],
        'current_page': page,
        'pages': pagination.pages,
        'event_types': [et[0] for et in event_types]
    })

@bp.route('/security-audit/export')
@login_required
@admin_required
def export_security_audit():
    severity = request.args.get('severity')
    event_type = request.args.get('event_type')
    date = request.args.get('date')
    
    query = SecurityAudit.query
    
    if severity:
        query = query.filter_by(severity=severity)
    if event_type:
        query = query.filter_by(event_type=event_type)
    if date:
        start_date = datetime.strptime(date, '%Y-%m-%d')
        end_date = start_date + timedelta(days=1)
        query = query.filter(SecurityAudit.created_at.between(start_date, end_date))
        
    query = query.order_by(SecurityAudit.created_at.desc())
    
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Time', 'Event Type', 'User', 'IP Address', 'User Agent', 'Severity', 'Details'])
    
    for audit in query.all():
        writer.writerow([
            audit.created_at.isoformat(),
            audit.event_type,
            User.query.get(audit.user_id).username if audit.user_id else None,
            audit.ip_address,
            audit.user_agent,
            audit.severity,
            json.dumps(audit.details) if audit.details else ''
        ])
    
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={
            'Content-Disposition': f'attachment; filename=security_audit_{datetime.now().strftime("%Y%m%d")}.csv'
        }
    )

@bp.route('/customization')
@admin_required
def customization():
    """Site customization page"""
    settings = SiteCustomization.get_active()
    return render_template('admin/customization.html', settings=settings)

@bp.route('/api/save-customization', methods=['POST'])
@admin_required
def save_customization():
    """Save customization settings"""
    data = request.get_json()
    
    # Validate and sanitize the data
    if not data or not isinstance(data, dict):
        return jsonify({'error': 'Invalid data format'}), 400
        
    try:
        settings = SiteCustomization.get_active()
        
        # Update settings
        for key, value in data.items():
            if hasattr(settings, key):
                setattr(settings, key, value)
        
        settings.updated_by = current_user.id
        db.session.commit()
        
        # Track the customization change
        log_admin_action(
            current_user,
            'site_customization',
            {'changes': data}
        )
        
        # Clear any cached templates
        if hasattr(current_app, 'jinja_env'):
            current_app.jinja_env.cache.clear()
        
        return jsonify({
            'message': 'Customization settings saved successfully',
            'settings': {
                'theme_name': settings.theme_name,
                'primary_color': settings.primary_color,
                'secondary_color': settings.secondary_color,
                'background_color': settings.background_color,
                'text_color': settings.text_color,
                'font_family': settings.font_family,
                'enable_dark_mode': settings.enable_dark_mode,
                'show_movie_ratings': settings.show_movie_ratings,
                'show_movie_views': settings.show_movie_views,
                'movies_per_page': settings.movies_per_page,
                'enable_comments': settings.enable_comments,
                'enable_user_profiles': settings.enable_user_profiles
            }
        })
    except Exception as e:
        current_app.logger.error(f'Error saving customization: {str(e)}')
        return jsonify({'error': 'Failed to save customization settings'}), 500

@bp.route('/content/movies')
@login_required
@admin_required
def manage_movies():
    return render_template('admin/movies.html',
                         active_tab='movies',
                         section_title='Movie Management',
                         content_type='Movie')

@bp.route('/content/tvshows')
@login_required
@admin_required
def manage_tvshows():
    return render_template('admin/tvshows.html',
                         active_tab='tvshows',
                         section_title='TV Show Management',
                         content_type='TV Show')

@bp.route('/content/anime')
@login_required
@admin_required
def manage_anime():
    return render_template('admin/anime.html',
                         active_tab='anime',
                         section_title='Anime Management',
                         content_type='Anime')

@bp.route('/api/content')
@login_required
@admin_required
def get_content():
    content_type = request.args.get('type', 'movie').lower()
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '')
    sort = request.args.get('sort', 'title')
    
    # Map content types to models
    content_models = {
        'movie': Movie,
        'tv show': TVShow,
        'anime': Anime
    }
    
    model = content_models.get(content_type)
    if not model:
        return jsonify({'error': 'Invalid content type'}), 400
    
    # Build query
    query = model.query
    
    # Apply search filter
    if search:
        query = query.filter(model.title.ilike(f'%{search}%'))
    
    # Apply sorting
    sort_mapping = {
        'title': model.title,
        'release_date': model.release_date,
        'rating': model.rating,
        'created_at': model.created_at
    }
    
    sort_column = sort_mapping.get(sort)
    if sort_column:
        query = query.order_by(sort_column)
    
    # Paginate results
    pagination = query.paginate(page=page, per_page=per_page)
    
    # Format response
    items = [{
        'id': item.id,
        'title': item.title,
        'release_date': item.release_date.isoformat() if item.release_date else None,
        'genre': item.genre,
        'rating': item.rating,
        'status': getattr(item, 'status', None) or getattr(item, 'current_status', None)
    } for item in pagination.items]
    
    return jsonify({
        'items': items,
        'total': pagination.total,
        'pages': pagination.pages,
        'current_page': page
    })

@bp.route('/api/content', methods=['POST'])
@login_required
@admin_required
def add_content():
    content_type = request.form.get('type', 'movie').lower()
    content_models = {
        'movie': Movie,
        'tv show': TVShow,
        'anime': Anime
    }
    
    model = content_models.get(content_type)
    if not model:
        return jsonify({'error': 'Invalid content type'}), 400
    
    try:
        # Create new content instance
        content = model()
        
        # Set common attributes
        content.title = request.form.get('title')
        content.description = request.form.get('description')
        content.release_date = parse_date(request.form.get('release_date'))
        content.duration = request.form.get('duration', type=int)
        content.genre = request.form.get('genre')
        content.rating = request.form.get('rating', type=float)
        content.trailer_url = request.form.get('trailer')
        
        # Handle thumbnail upload
        if 'thumbnail' in request.files:
            thumbnail = request.files['thumbnail']
            if thumbnail and allowed_file(thumbnail.filename):
                filename = secure_filename(thumbnail.filename)
                thumbnail_path = os.path.join(current_app.config['UPLOAD_FOLDER'], 'thumbnails', filename)
                thumbnail.save(thumbnail_path)
                content.thumbnail_url = f'/uploads/thumbnails/{filename}'
        
        # Set type-specific attributes
        if content_type == 'movie':
            content.is_3d = request.form.get('is_3d', type=bool)
            content.original_language = request.form.get('original_language')
            content.subtitles = parse_list(request.form.get('subtitles'))
            content.budget = request.form.get('budget', type=float)
            content.box_office = request.form.get('box_office', type=float)
            content.awards = request.form.get('awards')
        
        elif content_type == 'tv show':
            content.total_seasons = request.form.get('total_seasons', type=int)
            content.current_status = request.form.get('current_status')
            content.network = request.form.get('network')
            content.next_episode_date = parse_date(request.form.get('next_episode_date'))
            
            # Handle episodes per season
            episodes_per_season = {}
            for key in request.form:
                if key.startswith('episodes_season_'):
                    season_num = int(key.split('_')[-1])
                    episodes_per_season[season_num] = int(request.form[key])
            content.episodes_per_season = episodes_per_season
        
        elif content_type == 'anime':
            content.japanese_title = request.form.get('japanese_title')
            content.romanized_title = request.form.get('romanized_title')
            content.media_type = request.form.get('media_type')
            content.episodes = request.form.get('episodes', type=int)
            content.status = request.form.get('status')
            content.aired_from = parse_date(request.form.get('aired_from'))
            content.aired_to = parse_date(request.form.get('aired_to'))
            content.season = request.form.get('season')
            content.year = request.form.get('year', type=int)
            content.studios = parse_list(request.form.get('studios'))
            content.source = request.form.get('source')
            content.themes = parse_list(request.form.get('themes'))
            content.demographics = request.form.getlist('demographics')
            content.mal_id = request.form.get('mal_id', type=int)
            content.anilist_id = request.form.get('anilist_id', type=int)
        
        db.session.add(content)
        db.session.commit()
        
        return jsonify({
            'message': f'{content_type.title()} added successfully',
            'id': content.id
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

def parse_date(date_str):
    """Parse date string to date object"""
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return None

def parse_list(items_str):
    """Parse comma-separated string to list"""
    if not items_str:
        return []
    return [item.strip() for item in items_str.split(',') if item.strip()]

def allowed_file(filename):
    """Check if file extension is allowed"""
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
