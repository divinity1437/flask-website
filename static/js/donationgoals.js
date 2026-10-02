(() => {
    const widgets = [...document.querySelectorAll('[data-goal-widget]')];
    if (!widgets.length) return;

    const render = (goal) => {
        const raised = Number(goal.raised_amount) || 0;
        const target = Number(goal.goal_amount) || 0;
        const percent = target > 0 ? Math.min(100, Math.max(0, raised / target * 100)) : 0;
        const format = (value) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 }).format(value);

        widgets.forEach((widget) => {
            widget.querySelector('[data-goal-status]').textContent = goal.is_active ? 'In progress' : 'Goal completed';
            widget.querySelector('[data-goal-status]').dataset.loaded = 'true';
            widget.querySelector('[data-goal-title]').textContent = goal.title;
            widget.querySelector('[data-goal-raised]').textContent = `${format(raised)} ${goal.currency}`;
            widget.querySelector('[data-goal-target]').textContent = `${format(target)} ${goal.currency}`;
            widget.querySelector('[data-goal-progress]').style.width = `${percent}%`;
            widget.querySelector('[role="progressbar"]').setAttribute('aria-valuenow', String(Math.round(percent)));
        });
    };

    const refresh = async () => {
        try {
            const response = await fetch('/donationgoals/api/current', { cache: 'no-store' });
            if (!response.ok) throw new Error('Goal is not available');
            const data = await response.json();
            if (!data.available || !data.goal) throw new Error('Goal is not available');
            render(data.goal);
        } catch {
            widgets.forEach((widget) => {
                const status = widget.querySelector('[data-goal-status]');
                if (status.dataset.loaded !== 'true') status.textContent = 'Waiting for DonationAlerts goal update';
            });
        }
    };

    refresh();
    window.setInterval(refresh, 15000);
})();
