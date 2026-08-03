from app.api.admin import admin_bp
from app.api.datasets import datasets_bp
from app.api.jobs import jobs_bp
from app.api.molecules import molecules_bp
from app.api.operations import operations_bp
from app.api.poses import poses_bp
from app.api.projects import projects_bp
from app.api.releases import releases_bp
from app.api.scaffolds import scaffolds_bp


def register_api_blueprints(app):
    app.register_blueprint(releases_bp, url_prefix="/api")
    app.register_blueprint(datasets_bp, url_prefix="/api")
    app.register_blueprint(jobs_bp, url_prefix="/api")
    app.register_blueprint(scaffolds_bp, url_prefix="/api")
    app.register_blueprint(molecules_bp, url_prefix="/api")
    app.register_blueprint(poses_bp, url_prefix="/api")
    app.register_blueprint(projects_bp, url_prefix="/api")
    app.register_blueprint(operations_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/api")