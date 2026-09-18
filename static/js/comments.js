/**
 * Comment thread utilities.
 *
 * Used by student_dashboard.html for read-only comment preview
 * and faculty_feedback_detail.html for posting new comments.
 */

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Fetch and display comments for a feedback item (student view)
function loadComments(fbId, containerId) {
    fetch(`/faculty/feedback/${fbId}/comments`)
        .then(r => r.json())
        .then(comments => {
            const container = document.getElementById(containerId);
            if (!container || !comments.length) return;

            comments.forEach(c => {
                const div = document.createElement('div');
                div.className = 'comment-item';
                const date = new Date(c.created_at).toLocaleString();
                const authorLabel = c.author_type === 'faculty' ? 'Faculty' : 'Student';
                div.innerHTML = `<div class="comment-meta">${authorLabel} · ${date}</div><p style="white-space:pre-wrap;margin-top:0.25rem">${escapeHtml(c.text)}</p>`;
                container.appendChild(div);
            });
        })
        .catch(err => console.error('Failed to load comments:', err));
}

// Post a comment via AJAX (used by student view for read-only, faculty can post)
function postComment(fbId, text) {
    return fetch(`/faculty/feedback/${fbId}/comment`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text}),
    })
    .then(r => r.json())
    .then(data => {
        if (data.error) throw new Error(data.error);
        return data;
    });
}
