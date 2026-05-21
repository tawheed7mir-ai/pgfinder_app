self.addEventListener("push", (event) => {
    let payload = {};

    try {
        payload = event.data ? event.data.json() : {};
    } catch (_error) {
        payload = {
            title: "PG Finder",
            message: event.data ? event.data.text() : "You have a new notification."
        };
    }

    const title = payload.title || "PG Finder";
    const options = {
        body: payload.message || "You have a new notification.",
        icon: payload.icon || "/static/images/aesthetic-room-decor.jpg",
        badge: payload.badge || "/static/images/aesthetic-room-decor.jpg",
        data: {
            url: payload.url || "/"
        },
        tag: payload.type || "pgfinder-notification",
        renotify: true
    };

    event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
    event.notification.close();

    const targetUrl = new URL(event.notification.data?.url || "/", self.location.origin).href;

    event.waitUntil(
        clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if (client.url === targetUrl && "focus" in client) {
                    return client.focus();
                }
            }

            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }

            return undefined;
        })
    );
});
