// PM2 ecosystem config
module.exports = {
    apps: [
        {
            name: "atopsy-server",
            script: "dist/server.js",
            instances: "max",
            exec_mode: "cluster",
            env_production: {
                NODE_ENV: "production",
                PORT: 5000,
            },
            env_development: {
                NODE_ENV: "development",
                PORT: 5000,
            },
            max_memory_restart: "500M",
            log_date_format: "YYYY-MM-DD HH:mm:ss",
            error_file: "logs/pm2-error.log",
            out_file: "logs/pm2-out.log",
            merge_logs: true,
            watch: false,
            autorestart: true,
            max_restarts: 10,
            restart_delay: 4000,
        },
    ],
};
