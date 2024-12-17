@bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    stats = {
        'total_movies': Movie.query.count(),
        'new_movies_today': Movie.query.filter(Movie.created_at >= datetime.today()).count(),
        'total_users': User.query.count(),
        'new_users_today': User.query.filter(User.created_at >= datetime.today()).count(),
        'total_reviews': Review.query.count(),
        'pending_reviews': Review.query.filter_by(status='pending').count(),
        'storage_used': calculate_storage_usage(),
        'storage_percentage': calculate_storage_percentage()
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

@bp.route('/api/stats')
@login_required
@admin_required
def get_stats():
    # Return JSON stats for AJAX refresh
    return jsonify(stats_data)

@bp.route('/api/movies/<int:movie_id>', methods=['DELETE'])
@login_required
@admin_required
def delete_movie(movie_id):
    # Handle movie deletion
    return jsonify({'success': True})