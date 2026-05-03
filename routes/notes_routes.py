from flask import Blueprint, render_template, request, redirect, url_for, flash, send_from_directory, current_app
from flask_login import current_user
from models.notes_model import Notes
from extensions import db
import os
from werkzeug.utils import secure_filename
from routes.access_control import student_required

learning = Blueprint('learning', __name__)

@learning.route('/hub')
@student_required
def hub():
    # Fetch all notes for the logged-in user
    user_notes = Notes.query.filter_by(user_id=current_user.id).all()
    return render_template('learning_hub.html', notes=user_notes)

@learning.route('/upload', methods=['POST'])
@student_required
def upload_note():
    if 'file' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('learning.hub'))
    
    file = request.files['file']
    subject = request.form.get('subject')

    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('learning.hub'))

    if file and subject:
        filename = secure_filename(file.filename)
        
        # Use the config path we defined in app.py (static/uploads)
        upload_folder = current_app.config['UPLOAD_FOLDER']
        
        if not os.path.exists(upload_folder):
            os.makedirs(upload_folder)

        # Full path for saving the file
        file_path_full = os.path.join(upload_folder, filename)
        file.save(file_path_full)

        # Store only the filename in the DB for easier retrieval
        new_note = Notes(
            title=filename,
            subject=subject,
            file_path=filename, # Store just the name
            user_id=current_user.id
        )
        db.session.add(new_note)
        db.session.commit()
        flash('Note uploaded successfully!', 'success')
        
    return redirect(url_for('learning.hub'))

@learning.route('/download/<filename>')
@student_required
def download_file(filename):
    # Sends file as an attachment (Download)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename, as_attachment=True)

@learning.route('/view_note/<filename>')
@student_required
def view_note(filename):
    # Sends file to be opened in browser (Inline)
    return send_from_directory(current_app.config['UPLOAD_FOLDER'], filename)

@learning.route('/delete/<int:note_id>', methods=['POST'])
@student_required
def delete_note(note_id):
    note = Notes.query.get_or_404(note_id)
    
    if note.user_id != current_user.id:
        flash('Unauthorized action.', 'danger')
        return redirect(url_for('learning.hub'))

    # Construct the full path to delete the physical file
    full_path = os.path.join(current_app.config['UPLOAD_FOLDER'], note.file_path)
    
    if os.path.exists(full_path):
        os.remove(full_path)

    db.session.delete(note)
    db.session.commit()
    flash('Note deleted!', 'success')
    return redirect(url_for('learning.hub'))
