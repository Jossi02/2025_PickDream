package com.example.pick_dream

import com.example.pick_dream.model.Reservation
import com.example.pick_dream.notification.ReservationReminderAlarmGateway
import com.example.pick_dream.notification.ReservationReminderPlanner
import com.example.pick_dream.notification.ReservationReminderRecord
import com.example.pick_dream.notification.ReservationReminderRecordCodec
import com.example.pick_dream.notification.ReservationReminderReconciler
import com.example.pick_dream.notification.ReservationReminderStore
import com.example.pick_dream.util.ReservationTimeUtils
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.util.Calendar
import java.util.TimeZone

class ReservationReminderCoreTest {
    private val now = Calendar.getInstance(TimeZone.getTimeZone("Asia/Seoul")).apply {
        set(2099, Calendar.JULY, 10, 9, 0, 0)
        set(Calendar.MILLISECOND, 0)
    }.timeInMillis

    @Test
    fun stableIdentityDependsOnlyOnReservationDocumentId() {
        val first = reservation(id = "reservation-1", room = "7202", startHour = 11)
        val changed = reservation(id = "reservation-1", room = "4303", startHour = 14)

        val firstPlan = ReservationReminderPlanner.plan(first, now)!!
        val changedPlan = ReservationReminderPlanner.plan(changed, now)!!

        assertEquals(firstPlan.notificationId, changedPlan.notificationId)
        assertNull(ReservationReminderPlanner.plan(reservation(id = ""), now))
    }

    @Test
    fun plannerUsesTenMinuteLeadWhenEnoughTimeRemains() {
        val reservation = reservation(startHour = 11)
        val startAt = ReservationTimeUtils.parseReservationTimeMillis(reservation.startTime)!!
        val fifteenMinutesBefore = startAt - 15 * 60 * 1000L

        val planned = ReservationReminderPlanner.plan(reservation, fifteenMinutesBefore)!!

        assertEquals(startAt - 10 * 60 * 1000L, planned.reminderAtMillis)
    }

    @Test
    fun plannerNotifiesImmediatelyAtOrInsideTenMinuteBoundary() {
        val reservation = reservation(startHour = 11)
        val startAt = ReservationTimeUtils.parseReservationTimeMillis(reservation.startTime)!!
        val exactlyTenMinutesBefore = startAt - 10 * 60 * 1000L
        val fiveMinutesBefore = startAt - 5 * 60 * 1000L

        assertEquals(
            exactlyTenMinutesBefore,
            ReservationReminderPlanner.plan(reservation, exactlyTenMinutesBefore)!!.reminderAtMillis,
        )
        assertEquals(
            fiveMinutesBefore,
            ReservationReminderPlanner.plan(reservation, fiveMinutesBefore)!!.reminderAtMillis,
        )
    }

    @Test
    fun codecRoundTripsKoreanAndRejectsMalformedOrUnknownVersions() {
        val record = ReservationReminderPlanner.plan(reservation(id = "reservation|1"), now)!!
            .copy(title = "강의실|알림", body = "집현관 202호|곧 시작", delivered = true)

        assertEquals(record, ReservationReminderRecordCodec.decode(ReservationReminderRecordCodec.encode(record)))
        assertNull(ReservationReminderRecordCodec.decode("not-a-record"))
        assertNull(ReservationReminderRecordCodec.decode("2|a|b|c|d|e|1|2|3|x|y|false"))
    }

    @Test
    fun reconcileIsIdempotentAndStoresBeforeScheduling() {
        val store = FakeStore()
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }
        val reservation = reservation(id = "reservation-1")

        reconciler.reconcile(listOf(reservation, reservation), enabled = true)
        reconciler.reconcile(listOf(reservation), enabled = true)

        assertEquals(1, store.records.size)
        assertEquals(1, gateway.scheduled.size)
        assertTrue(gateway.scheduleSawPersistedRecord)
        assertTrue(gateway.cancelled.isEmpty())
    }

    @Test
    fun reconcileResolvesNotificationIdHashCollisions() {
        val store = FakeStore()
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }

        // These strings intentionally have the same Java/Kotlin String hash code.
        reconciler.reconcile(
            listOf(reservation(id = "Aa"), reservation(id = "BB", room = "4303")),
            enabled = true,
        )

        assertEquals(2, store.records.map { it.notificationId }.distinct().size)
    }

    @Test
    fun failedPersistentWriteDoesNotScheduleAnUntrackedAlarm() {
        val store = FakeStore().apply { writesSucceed = false }
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }

        reconciler.reconcile(listOf(reservation()), enabled = true)

        assertTrue(store.records.isEmpty())
        assertTrue(gateway.scheduled.isEmpty())
    }

    @Test
    fun reconcileCollapsesDuplicatePersistedSchedulesForTheSameReservation() {
        val reservation = reservation(id = "reservation-1")
        val planned = ReservationReminderPlanner.plan(reservation, now)!!
        val staleDuplicate = planned.copy(notificationId = planned.notificationId + 1)
        val store = FakeStore(listOf(planned, staleDuplicate))
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }

        reconciler.reconcile(listOf(reservation), enabled = true)

        assertEquals(1, store.records.size)
        assertEquals(1, gateway.scheduled.size)
        assertEquals(1, gateway.cancelled.size)
    }

    @Test
    fun reconcileChangedCancelledAndDisabledReservationsRemoveStaleAlarms() {
        val store = FakeStore()
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }
        val original = reservation(id = "reservation-1", room = "7202", startHour = 11)
        val changed = reservation(id = "reservation-1", room = "4303", startHour = 14)

        reconciler.reconcile(listOf(original), enabled = true)
        reconciler.reconcile(listOf(changed), enabled = true)

        assertEquals(2, gateway.scheduled.size)
        assertEquals(0, gateway.cancelled.size)
        assertEquals("4303", store.records.single().roomId)

        reconciler.reconcile(listOf(changed.copy(status = "취소")), enabled = true)
        assertTrue(store.records.isEmpty())
        assertEquals(1, gateway.cancelled.size)

        reconciler.reconcile(listOf(original), enabled = true)
        reconciler.reconcile(emptyList(), enabled = false)
        assertTrue(store.records.isEmpty())
        assertEquals(2, gateway.cancelled.size)
    }

    @Test
    fun restoreRearmsUndeliveredFutureRecordAndRemovesExpiredRecord() {
        val future = ReservationReminderPlanner.plan(reservation(id = "future", startHour = 11), now)!!
        val expired = future.copy(
            reservationId = "expired",
            startTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 10, 7, 0),
            endTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 10, 8, 0),
            startAtMillis = now - 2 * 60 * 60 * 1000L,
            reminderAtMillis = now - 2 * 60 * 60 * 1000L - 10 * 60 * 1000L,
        )
        val store = FakeStore(listOf(future, expired))
        val gateway = FakeGateway(store)
        val reconciler = ReservationReminderReconciler(store, gateway) { now }

        reconciler.restorePersisted()

        assertEquals(listOf("future"), gateway.scheduled.map { it.reservationId })
        assertEquals(listOf("future"), store.records.map { it.reservationId })
    }

    @Test
    fun takeForDeliveryMarksRecordDeliveredAndAllowsStartTimeGrace() {
        val record = ReservationReminderPlanner.plan(reservation(id = "reservation-1", startHour = 11), now)!!
        val store = FakeStore(listOf(record))
        val gateway = FakeGateway(store)
        val startTime = record.startAtMillis
        val reconciler = ReservationReminderReconciler(store, gateway) { startTime }

        val delivered = reconciler.takeForDelivery(record.reservationId, record.notificationId)

        assertEquals(record.reservationId, delivered?.reservationId)
        assertTrue(store.records.single().delivered)
        assertNull(reconciler.takeForDelivery(record.reservationId, record.notificationId))
        assertFalse(ReservationReminderPlanner.isWithinDeliveryGrace(record, record.startAtMillis + 30 * 60 * 1000L + 1))
    }

    private fun reservation(
        id: String = "reservation-1",
        room: String = "7202",
        startHour: Int = 11,
    ): Reservation = Reservation(
        documentId = id,
        userID = "20201234",
        roomID = room,
        startTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 10, startHour, 0),
        endTime = ReservationTimeUtils.toReservationTimeString(2099, 7, 10, startHour + 2, 0),
        status = "대기",
    )

    private class FakeStore(records: List<ReservationReminderRecord> = emptyList()) : ReservationReminderStore {
        val records = records.toMutableList()
        var writesSucceed = true

        override fun loadAll(): List<ReservationReminderRecord> = records.toList()

        override fun save(record: ReservationReminderRecord): Boolean {
            if (!writesSucceed) return false
            remove(record.reservationId)
            records += record
            return true
        }

        override fun remove(reservationId: String): Boolean {
            if (!writesSucceed) return false
            records.removeAll { it.reservationId == reservationId }
            return true
        }
    }

    private class FakeGateway(private val store: FakeStore) : ReservationReminderAlarmGateway {
        val scheduled = mutableListOf<ReservationReminderRecord>()
        val cancelled = mutableListOf<Pair<String, Int>>()
        var scheduleSawPersistedRecord = false

        override fun schedule(record: ReservationReminderRecord) {
            scheduleSawPersistedRecord = store.records.any { it.reservationId == record.reservationId }
            scheduled += record
        }

        override fun cancel(reservationId: String, notificationId: Int) {
            cancelled += reservationId to notificationId
        }
    }
}
