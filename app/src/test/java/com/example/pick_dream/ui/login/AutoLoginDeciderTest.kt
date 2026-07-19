package com.example.pick_dream.ui.login

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class AutoLoginDeciderTest {
    @Test
    fun unauthenticatedUserNeverEntersApp() {
        assertFalse(AutoLoginDecider.shouldEnterApp(false, false, false))
        assertFalse(AutoLoginDecider.shouldEnterApp(true, false, false))
        assertFalse(AutoLoginDecider.shouldEnterApp(false, false, true))
        assertFalse(AutoLoginDecider.shouldEnterApp(true, false, true))
    }

    @Test
    fun autoLoginAllowsAuthenticatedColdStart() {
        assertTrue(AutoLoginDecider.shouldEnterApp(true, true, false))
    }

    @Test
    fun activeManualSessionAllowsAuthenticatedResume() {
        assertTrue(AutoLoginDecider.shouldEnterApp(false, true, true))
    }

    @Test
    fun uncheckedColdStartReturnsToLogin() {
        assertFalse(AutoLoginDecider.shouldEnterApp(false, true, false))
    }
}
