import { Role } from "@prisma/client";
import bcrypt from "bcryptjs";
import { prisma } from "../src/config/database";

async function main() {
    console.log("🌱 Seeding database...");

    // Create admin user
    const adminPassword = await bcrypt.hash("Admin@123456", 12);

    const admin = await prisma.user.upsert({
        where: { email: "admin@atopsy.io" },
        update: {},
        create: {
            email: "admin@atopsy.io",
            passwordHash: adminPassword,
            firstName: "System",
            lastName: "Admin",
            role: Role.ADMIN,
            isActive: true,
            isEmailVerified: true,
        },
    });

    console.log(`✅ Admin user created: ${admin.email}`);

    // Create investigator
    const investigatorPassword = await bcrypt.hash("Invest@123456", 12);

    const investigator = await prisma.user.upsert({
        where: { email: "investigator@atopsy.io" },
        update: {},
        create: {
            email: "investigator@atopsy.io",
            passwordHash: investigatorPassword,
            firstName: "John",
            lastName: "Doe",
            role: Role.INVESTIGATOR,
            isActive: true,
            isEmailVerified: true,
        },
    });

    console.log(`✅ Investigator created: ${investigator.email}`);

    // Create forensic expert
    const expertPassword = await bcrypt.hash("Expert@123456", 12);

    const expert = await prisma.user.upsert({
        where: { email: "expert@atopsy.io" },
        update: {},
        create: {
            email: "expert@atopsy.io",
            passwordHash: expertPassword,
            firstName: "Jane",
            lastName: "Smith",
            role: Role.FORENSIC_EXPERT,
            isActive: true,
            isEmailVerified: true,
        },
    });

    console.log(`✅ Forensic expert created: ${expert.email}`);

    console.log("🌱 Seeding complete!");
}

main()
    .catch((e) => {
        console.error("❌ Seed error:", e);
        process.exit(1);
    })
    .finally(async () => {
        await prisma.$disconnect();
    });
