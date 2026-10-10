#ifndef XMC_META_H
#define XMC_META_H

#include <stdint.h>
#include "metadata.h"

/* On-flash append-only metadata log (see common/metadata.h). */

/* Read the newest valid record. Returns 1 if found, 0 if the log is empty
 * (caller should use defaults). */
int meta_log_read(meta_record_t *out);

/* Append a record (seq is filled by the caller; must be > last seq).
 * Returns 0 on success. Full banks roll over without erasing the latest record. */
int meta_log_append(meta_record_t *rec);

#endif
