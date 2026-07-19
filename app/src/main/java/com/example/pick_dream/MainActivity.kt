package com.example.pick_dream

import android.content.Context
import android.os.Bundle
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.navigation.NavController
import androidx.navigation.fragment.NavHostFragment
import com.example.pick_dream.databinding.ActivityMainBinding
import com.example.pick_dream.notification.PickDreamNotificationManager
import com.example.pick_dream.notification.ReservationExactAlarmAccess
import com.example.pick_dream.notification.ReservationNotificationPreferences
import com.example.pick_dream.notification.ReservationReminderScheduler
import com.example.pick_dream.notification.ReservationReminderSync
import com.example.pick_dream.ui.home.search.LectureRoomRepository
import com.example.pick_dream.ui.login.AuthenticatedEntryGuard
import com.google.android.material.bottomnavigation.BottomNavigationView
import kotlinx.coroutines.launch

class MainActivity : AppCompatActivity() {

    private lateinit var binding: ActivityMainBinding
    private lateinit var navController: NavController

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (AuthenticatedEntryGuard.redirectToLoginIfRequired(this)) return

        binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)

        // 앱 시작 시 강의실 및 찜 목록 데이터 미리 로드
        PickDreamNotificationManager.createChannels(this)
        ReservationReminderScheduler.restorePersisted(this)
        lifecycleScope.launch {
            ReservationReminderSync.reconcileCurrentUser(this@MainActivity)
        }
        LectureRoomRepository.fetchRooms()
        LectureRoomRepository.fetchFavoriteIds()

        val navHostFragment = supportFragmentManager
            .findFragmentById(R.id.nav_host_fragment_activity_main) as NavHostFragment
        navController = navHostFragment.navController

        setupBottomNavigation()
        checkClassroomUsageTime()
        showExactAlarmExplanationIfNeeded()
    }

    override fun onResume() {
        super.onResume()
        if (ReservationExactAlarmAccess.canScheduleExactAlarms(this)) {
            ReservationReminderScheduler.restorePersisted(this)
        }
    }

    private fun showExactAlarmExplanationIfNeeded() {
        if (!ReservationNotificationPreferences.isReservationUsageTimeEnabled(this)) return
        if (!ReservationExactAlarmAccess.shouldShowInitialExplanation(this)) return

        ReservationExactAlarmAccess.markInitialExplanationShown(this)
        val requestIntent = ReservationExactAlarmAccess.requestIntent(this) ?: return
        AlertDialog.Builder(this)
            .setTitle("정확한 알림 권한")
            .setMessage(
                "강의실 이용 알림을 예약 시간에 맞춰 받으려면 " +
                    "'알람 및 리마인더' 권한을 허용해 주세요. " +
                    "허용하지 않아도 알림은 동작하지만 늦을 수 있습니다."
            )
            .setPositiveButton("설정 열기") { _, _ -> startActivity(requestIntent) }
            .setNegativeButton("나중에", null)
            .show()
    }

    /**
     * BottomNavigationView 아이콘 및 탭 선택 이벤트를 설정합니다.
     */
    private fun setupBottomNavigation() {
        val navView: BottomNavigationView = binding.navView
        updateNavIcons(navView, navView.selectedItemId)

        navView.setOnItemSelectedListener { item ->
            updateNavIcons(navView, item.itemId)
            when (item.itemId) {
                R.id.navigation_home -> navController.navigate(R.id.homeFragment)
                R.id.navigation_favorite -> navController.navigate(R.id.favoriteFragment)
                R.id.navigation_mypage -> navController.navigate(R.id.mypageFragment)
            }
            true
        }
    }

    /**
     * 선택된 탭에 맞게 BottomNavigationView의 아이콘을 filled/outline으로 교체합니다.
     * @param navView 대상 BottomNavigationView
     * @param selectedId 현재 선택된 메뉴 아이템 ID
     */
    private fun updateNavIcons(navView: BottomNavigationView, selectedId: Int) {
        navView.menu.findItem(R.id.navigation_home).setIcon(
            if (selectedId == R.id.navigation_home) R.drawable.ic_home_filled else R.drawable.ic_home
        )
        navView.menu.findItem(R.id.navigation_favorite).setIcon(
            if (selectedId == R.id.navigation_favorite) R.drawable.ic_favorite_filled else R.drawable.ic_favorite
        )
        navView.menu.findItem(R.id.navigation_mypage).setIcon(
            if (selectedId == R.id.navigation_mypage) R.drawable.ic_mypage_filled else R.drawable.ic_person
        )
    }

    /**
     * 앱 재시작 시, 강의실 사용 종료 후 리뷰를 아직 보여주지 않았다면 ReviewFragment로 이동합니다.
     */
    private fun checkClassroomUsageTime() {
        val sharedPrefs = getSharedPreferences("ClassroomPrefs", Context.MODE_PRIVATE)
        val lastEndTime = sharedPrefs.getLong("last_end_time", 0)
        val hasShownReview = sharedPrefs.getBoolean("has_shown_review", false)
        val lastRoomId = sharedPrefs.getString("last_room_id", null)
        val currentTime = System.currentTimeMillis()

        if (lastRoomId != null && lastEndTime > 0 && !hasShownReview && currentTime > lastEndTime) {
            val bundle = Bundle().apply { putString("roomId", lastRoomId) }
            navController.navigate(R.id.reviewFragment, bundle)
            sharedPrefs.edit().putBoolean("has_shown_review", true).apply()
        }
    }
}
