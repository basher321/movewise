// The only file pages and components may import from. Every action calls the FastAPI backend
// through ./http (spec B10). Errors are ApiError with the backend's code and status.

export * from "./types";
export { ApiError, isApiError, NETWORK_MESSAGE, type ErrorCode } from "./errors";
export { apiUrl } from "./http/client";

// settings / licence / branding
export {
  getPublicSettings,
  getSettings,
  saveSettings,
  uploadBrandingImage,
  clearBrandingImage,
  getLicence,
  getFullLicence,
  applyLicenceKey,
  sendTestEmail,
  sendTestWhatsapp,
  testAiProvider,
  type BrandingKind,
} from "./http/settings";

// auth
export {
  applicantSignUp,
  applicantSignIn,
  type SignUpInput,
  getSetupStatus,
  adminSignUp,
  adminSignIn,
  superAdminSignUp,
  superAdminSignIn,
  updateMyAdminAccount,
  changeMyAdminPassword,
  signOut,
  getSession,
  getPasswordOptions,
  forgotPassword,
  resetPassword,
  type ResetKind,
  updateMyProfile,
  changeMyPassword,
} from "./http/auth";

// catalog / match / agent / fees. There is no delete: items are hidden or closed.
export {
  listCourseGroups,
  getCourse,
  listUniversities,
  getUniversity,
  listVacancies,
  getVacancy,
  listVisaPrograms,
  getVisaProgram,
  listRemoteJobs,
  getRemoteJob,
  getSuccessStories,
  getCatalogOptions,
  matchUniversities,
  matchVacancies,
  matchVisaPrograms,
  matchRemoteJobs,
  askAgent,
  rememberAgentInputs,
  lastAgentInputs,
  listAdminCourseGroups,
  saveCourseGroup,
  listAdminCourses,
  saveCourse,
  listAdminUniversities,
  saveUniversity,
  listAdminVacancies,
  saveVacancy,
  listAdminVisaPrograms,
  saveVisaProgram,
  listAdminRemoteJobs,
  saveRemoteJob,
  getFees,
  saveFees,
  resetFees,
} from "./http/catalog";

// applications / cases / documents
export {
  startApplication,
  myApplications,
  getMyApplication,
  withdrawApplication,
  payApplicationFee,
  uploadDocument,
  submitDocuments,
  MAX_UPLOAD_BYTES,
  listApplications,
  getApplication,
  changeStage,
  changeStatus,
  updateCase,
  addInternalNote,
  sendCaseEmail,
  listApplicantAccounts,
  resetApplicantPassword,
  listDocuments,
  verifyDocument,
  rejectDocument,
} from "./http/applications";

// money
export {
  getMyPayment,
  myInvoices,
  getMyInvoice,
  requestRefund,
  listPendingPayments,
  verifyPayment,
  rejectPayment,
  listRefunds,
  approveRefund,
  declineRefund,
  listOutstanding,
  sendPaymentReminder,
  listLedger,
  ledgerSummary,
  addLedgerEntry,
  reverseLedgerEntry,
  ledgerCsvUrl,
  listInvoices,
  getInvoice,
} from "./http/money";

// courses / notifications / enquiries / team / audit. Admins are never deleted.
export {
  enrol,
  myEnrolments,
  listEnrolments,
  approveCertificate,
  verifyCertificate,
  listNotifications,
  resendNotification,
  submitEnquiry,
  listEnquiries,
  addEnquiry,
  updateEnquiry,
  addEnquiryNote,
  listAdmins,
  approveAdmin,
  deactivateAdmin,
  resetStaffPassword,
  reactivateAdmin,
  setRole,
  setSections,
  listAssignableAdmins,
  listAudit,
  AUDIT_ROWS_PER_PAGE,
} from "./http/other";

// partner agents and commissions (B16). Agents are switched off, never deleted.
export {
  listAgents,
  createAgent,
  updateAgent,
  setApplicationAgent,
  listCommissions,
  setCommission,
  payCommission,
  cancelCommission,
} from "./http/agents";

// B2B partners and logos (B18). Partners are switched off, never deleted.
export {
  listPublicPartners,
  listPartners,
  createPartner,
  updatePartner,
  uploadPartnerLogo,
  clearPartnerLogo,
} from "./http/partners";

// agreements and other documents of agents and partners (B21). Archived, never deleted.
export {
  listPartyDocuments,
  uploadPartyDocument,
  archivePartyDocument,
  MAX_PARTY_DOCUMENT_BYTES,
} from "./http/partyDocuments";

// Excel upload of listings (B23)
export { previewImport, commitImport, downloadImportTemplate, MAX_IMPORT_BYTES } from "./http/imports";

// certificates, completion letters and client messages (B20)
export {
  getEnrolmentCertificate,
  enrolmentCertificatePdfUrl,
  sendEnrolmentCertificate,
  getCaseLetter,
  caseLetterPdfUrl,
  issueCaseLetter,
  sendCaseLetter,
  myCertificatePdfUrl,
  myLetterPdfUrl,
  sendClientMessage,
  previewGroupMessage,
  sendGroupMessage,
} from "./http/certificates";
