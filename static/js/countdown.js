/**
 * Countdown timer — client-side ticking + server-fetched deadlines.
 *
 * Usage: startCountdown(fbId, elementId)
 *   Reads the deadline from the server API and ticks down in real time.
 */

function formatCountdown(seconds) {
    if (seconds <= 0) return 'Expired';

    const days = Math.floor(seconds / 86400);
    const hours = Math.floor((seconds % 86400) / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = seconds % 60;

    if (days > 0) return `${days}d ${hours}h ${mins}m`;
    if (hours > 0) return `${hours}h ${mins}m ${secs}s`;
    return `${mins}m ${secs}s`;
}

function startCountdown(fbId, elementId) {
    const el = document.getElementById(elementId);
    if (!el) return;

    function tick() {
        fetch(`/faculty/api/countdown/${fbId}`)
            .then(r => r.json())
            .then(data => {
                if (data.error || data.seconds_remaining === undefined) {
                    el.textContent = '—';
                    return;
                }

                const remaining = data.seconds_remaining;
                el.textContent = formatCountdown(remaining);

                // Update color class based on status
                let cls = 'countdown-badge countdown-resolved';
                if (data.status === 'overdue' || data.status === 'escalated') {
                    cls = 'countdown-badge countdown-overdue';
                } else if (remaining < 3600) {
                    // Less than 1 hour remaining
                    cls = 'countdown-badge countdown-warning';
                }
                el.className = cls;

                // Update label on detail page
                const labelEl = document.getElementById(`countdown-label-${fbId}`);
                if (labelEl) {
                    const deadlineType = data.deadline_type === 'escalation' ? 'Escalation Deadline' : 'Review Deadline';
                    labelEl.textContent = `${deadlineType} · ${data.status.charAt(0).toUpperCase() + data.status.slice(1)}`;

                    // Update display container class
                    const display = document.getElementById('countdown-display');
                    if (display) {
                        display.className = 'countdown-display';
                        if (data.status === 'overdue' || data.status === 'escalated') {
                            display.classList.add('overdue');
                        } else if (remaining < 3600) {
                            display.classList.add('warning');
                        }
                    }
                }

                // Stop ticking when expired and not escalated
                if (remaining <= 0 && data.status !== 'escalated') {
                    clearInterval(interval);
                }
            })
            .catch(() => {
                el.textContent = '—';
            });
    }

    tick(); // initial fetch
    const interval = setInterval(tick, 1000); // tick every second
}

// Auto-start countdowns on the dashboard (all feedback rows)
function startDashboardCountdowns() {
    document.querySelectorAll('[data-fb-id]').forEach(row => {
        const fbId = row.getAttribute('data-fb-id');
        const el = document.getElementById(`countdown-${fbId}`);
        if (el && !el.dataset.started) {
            el.dataset.started = 'true';
            startCountdown(fbId, `countdown-${fbId}`);
        }

        // Also student dashboard countdowns
        const studentEl = document.getElementById(`countdown-student-${fbId}`);
        if (studentEl && !studentEl.dataset.started) {
            studentEl.dataset.started = 'true';
            startCountdown(fbId, `countdown-student-${fbId}`);
        }
    });
}

// Run on page load
document.addEventListener('DOMContentLoaded', startDashboardCountdowns);
