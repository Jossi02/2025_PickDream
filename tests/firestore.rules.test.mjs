import { readFileSync } from "node:fs";
import { after, before, test } from "node:test";

import {
  assertFails,
  assertSucceeds,
  initializeTestEnvironment,
} from "@firebase/rules-unit-testing";
import {
  collection,
  deleteDoc,
  doc,
  getDoc,
  getDocs,
  setDoc,
  updateDoc,
} from "firebase/firestore";

const projectId = "pickdreamtest";
let testEnv;

before(async () => {
  testEnv = await initializeTestEnvironment({
    projectId,
    firestore: {
      rules: readFileSync("firestore.rules", "utf8"),
    },
  });
});

after(async () => {
  await testEnv.cleanup();
});

async function seed() {
  await testEnv.clearFirestore();
  await testEnv.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    await setDoc(doc(db, "User", "uid-1"), {
      studentId: "20201234",
      name: "User One",
      favoriteRooms: [],
    });
    await setDoc(doc(db, "User", "uid-2"), {
      studentId: "20205678",
      name: "User Two",
      favoriteRooms: [],
    });
    await setDoc(doc(db, "rooms", "room-7202"), {
      roomID: "7202",
      name: "7202 강의실",
    });
    await setDoc(doc(db, "Notices", "notice-1"), {
      title: "Notice",
    });
    await setDoc(doc(db, "Reservations", "owned-reservation"), {
      ownerUid: "uid-1",
      userID: "20201234",
      roomID: "7202",
      startTime: "2099년 7월 12일 오후 1시 0분 0초 UTC+9",
      endTime: "2099년 7월 12일 오후 3시 0분 0초 UTC+9",
      eventParticipants: 3,
      status: "대기",
    });
    await setDoc(doc(db, "Reservations", "legacy-reservation"), {
      userID: "20201234",
      roomID: "5101",
      startTime: "2099년 7월 13일 오후 1시 0분 0초 UTC+9",
      endTime: "2099년 7월 13일 오후 3시 0분 0초 UTC+9",
      eventParticipants: 3,
      status: "대기",
    });
    await setDoc(doc(db, "Reviews", "owned-review"), {
      ownerUid: "uid-1",
      userID: "20201234",
      roomID: "7202",
      rating: 5,
      comment: "좋아요",
    });
    await setDoc(doc(db, "ChatHistory", "20201234"), {
      messages: [],
    });
    await setDoc(doc(db, "PendingReservations", "20201234"), {
      room: "7202",
    });
  });
}

function reservationData(overrides = {}) {
  return {
    ownerUid: "uid-1",
    userID: "20201234",
    roomID: "4303",
    startTime: "2099년 7월 14일 오후 1시 0분 0초 UTC+9",
    endTime: "2099년 7월 14일 오후 3시 0분 0초 UTC+9",
    eventParticipants: 4,
    status: "대기",
    ...overrides,
  };
}

test("public data requires authentication", async () => {
  await seed();
  const anonymousDb = testEnv.unauthenticatedContext().firestore();
  const userDb = testEnv.authenticatedContext("uid-1").firestore();

  await assertFails(getDoc(doc(anonymousDb, "rooms", "room-7202")));
  await assertFails(getDocs(collection(anonymousDb, "Reservations")));
  await assertSucceeds(getDoc(doc(userDb, "rooms", "room-7202")));
  await assertSucceeds(getDoc(doc(userDb, "Notices", "notice-1")));
  await assertSucceeds(getDocs(collection(userDb, "Reviews")));
});

test("users can read only their profile and update only favorites", async () => {
  await seed();
  const db = testEnv.authenticatedContext("uid-1").firestore();

  await assertSucceeds(getDoc(doc(db, "User", "uid-1")));
  await assertFails(getDoc(doc(db, "User", "uid-2")));
  await assertSucceeds(
    updateDoc(doc(db, "User", "uid-1"), { favoriteRooms: ["7202"] })
  );
  await assertFails(
    updateDoc(doc(db, "User", "uid-1"), { studentId: "20205678" })
  );
  await assertFails(
    setDoc(doc(db, "User", "new-user"), { studentId: "99999999" })
  );
});

test("reservation writes enforce both ownerUid and student ID", async () => {
  await seed();
  const ownerDb = testEnv.authenticatedContext("uid-1").firestore();
  const otherDb = testEnv.authenticatedContext("uid-2").firestore();

  await assertSucceeds(
    setDoc(doc(ownerDb, "Reservations", "new-reservation"), reservationData())
  );
  await assertFails(
    setDoc(
      doc(ownerDb, "Reservations", "spoofed-owner"),
      reservationData({ ownerUid: "uid-2" })
    )
  );
  await assertFails(
    setDoc(
      doc(ownerDb, "Reservations", "spoofed-student"),
      reservationData({ userID: "20205678" })
    )
  );
  await assertSucceeds(
    updateDoc(doc(ownerDb, "Reservations", "owned-reservation"), {
      eventParticipants: 5,
    })
  );
  await assertFails(
    updateDoc(doc(ownerDb, "Reservations", "owned-reservation"), {
      ownerUid: "uid-2",
    })
  );
  await assertFails(
    deleteDoc(doc(otherDb, "Reservations", "owned-reservation"))
  );
  await assertSucceeds(
    deleteDoc(doc(ownerDb, "Reservations", "owned-reservation"))
  );
});

test("legacy owned reservations remain deletable but cannot be rewritten", async () => {
  await seed();
  const db = testEnv.authenticatedContext("uid-1").firestore();

  await assertFails(
    updateDoc(doc(db, "Reservations", "legacy-reservation"), {
      eventParticipants: 6,
    })
  );
  await assertSucceeds(
    deleteDoc(doc(db, "Reservations", "legacy-reservation"))
  );
});

test("review ownership and server-only collections are enforced", async () => {
  await seed();
  const ownerDb = testEnv.authenticatedContext("uid-1").firestore();
  const otherDb = testEnv.authenticatedContext("uid-2").firestore();

  await assertSucceeds(
    setDoc(doc(ownerDb, "Reviews", "new-review"), {
      ownerUid: "uid-1",
      userID: "20201234",
      roomID: "7202",
      rating: 4,
      comment: "좋아요",
    })
  );
  await assertFails(
    deleteDoc(doc(otherDb, "Reviews", "owned-review"))
  );
  await assertSucceeds(
    deleteDoc(doc(ownerDb, "Reviews", "owned-review"))
  );
  await assertFails(getDoc(doc(ownerDb, "ChatHistory", "20201234")));
  await assertFails(getDoc(doc(ownerDb, "PendingReservations", "20201234")));
});
